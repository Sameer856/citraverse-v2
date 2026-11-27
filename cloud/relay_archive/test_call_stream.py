import asyncio,base64,json,struct
import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus,ConnectionClosed
from test_relay import servers,DEVICE_KEY,APP_KEY,AUTH,PREFIX

HEADERS={**AUTH,'X-Call-Token':'b'*32}
async def answer(pcb, command, status=200):
    await pcb.send(json.dumps({'kind':'response','id':command['id'],'status':status,'body':base64.b64encode(b'OK').decode()}))
async def ready(pcb, phone):
    command=json.loads(await pcb.recv());assert command['path']=='/call/pcm?after=0'
    assert command['call_token']=='b'*32
    await answer(pcb,command)
    response=json.loads(await phone.recv());assert response['kind']=='ready' and response['max_inflight']==4

def frame(sequence, pcm):return struct.pack('<2I',0x31545450,sequence)+pcm

@pytest.mark.asyncio
async def test_stream_auth_pipeline_exact_pcm_and_bounded_credit():
    async with servers() as (a,b):
        with pytest.raises(InvalidStatus):
            async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers={'Authorization':'Bearer '+DEVICE_KEY,'X-Call-Token':'b'*32}):pass
        with pytest.raises(InvalidStatus):
            async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers=AUTH):pass
        async with connect(f'ws://127.0.0.1:{a}{PREFIX}/link',additional_headers={'Authorization':'Bearer '+DEVICE_KEY}) as pcb:
            async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers=HEADERS) as phone:
                await ready(pcb,phone)
                bodies=[struct.pack('<4h',-32768,-1,0,32767),b'\x12\x34'*1920,b'\x56\x78'*1600,b'\0\0']
                for index,pcm in enumerate(bodies,1):await phone.send(frame(index,pcm))
                commands=[json.loads(await asyncio.wait_for(pcb.recv(),.2)) for _ in range(4)]
                assert [base64.b64decode(c['body']) for c in commands]==bodies
                assert all(c['path']=='/call/pcm' and c['method']=='POST' for c in commands)
                # Four requests reached the PCB before any reply: no round-trip stall.
                await phone.send(frame(5,b'\0\0'))
                ack=json.loads(await phone.recv());assert ack=={'kind':'ack','sequence':5,'status':429,'accepted_samples':0}
                for command in reversed(commands):await answer(pcb,command)
                acks=[json.loads(await phone.recv()) for _ in range(4)]
                assert {x['sequence']:x['accepted_samples'] for x in acks}=={1:4,2:1920,3:1600,4:1}
                # Duplicate sequence cannot replay speaker samples.
                await phone.send(frame(5,b'\0\0'))
                with pytest.raises(ConnectionClosed):await phone.recv()

@pytest.mark.asyncio
async def test_stream_rejects_expired_call_and_malformed_pcm():
    async with servers() as (a,b):
        async with connect(f'ws://127.0.0.1:{a}{PREFIX}/link',additional_headers={'Authorization':'Bearer '+DEVICE_KEY}) as pcb:
            async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers=HEADERS) as phone:
                command=json.loads(await pcb.recv());await answer(pcb,command,403)
                assert json.loads(await phone.recv())=={'kind':'error','status':403}
                with pytest.raises(ConnectionClosed):await phone.recv()
            for payload in (frame(1,b'x'),frame(1,b'\0'*3842),frame(2,b'\0\0')):
                async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers=HEADERS) as phone:
                    await ready(pcb,phone);await phone.send(payload)
                    with pytest.raises(ConnectionClosed):await phone.recv()

@pytest.mark.asyncio
async def test_stream_timeout_is_explicit_and_never_replays_uncertain_pcm():
    async with servers() as (a,b):
        async with connect(f'ws://127.0.0.1:{a}{PREFIX}/link',additional_headers={'Authorization':'Bearer '+DEVICE_KEY}) as pcb:
            async with connect(f'ws://127.0.0.1:{b}{PREFIX}/call/stream',additional_headers=HEADERS) as phone:
                await ready(pcb,phone);await phone.send(frame(1,b'\0\0'))
                command=json.loads(await pcb.recv());assert command['path']=='/call/pcm'
                ack=json.loads(await phone.recv());assert ack['status']==504 and ack['accepted_samples']==0
                with pytest.raises(asyncio.TimeoutError):await asyncio.wait_for(pcb.recv(),.05)
