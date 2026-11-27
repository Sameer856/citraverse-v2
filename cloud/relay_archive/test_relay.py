import asyncio
import base64
import hashlib
import json
import socket
import struct
import time
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app import MemoryBus, RedisBus, Settings, create_app

DEVICE_KEY = "d" * 48
APP_KEY = "a" * 48
DEVICE = "citra-pcb-01"
AUTH = {"Authorization": "Bearer " + APP_KEY}
PREFIX = "/v1/devices/" + DEVICE


@pytest.mark.asyncio
async def test_production_redis_subscription_registers_expected_channel():
    class Subscription:
        async def subscribe(self, name):
            assert name == "citraverse:relay:v1"
        async def listen(self):
            await asyncio.sleep(100)
            yield {"type":"unused"}
        async def aclose(self):
            pass
    sub = Subscription()
    bus = RedisBus.__new__(RedisBus)
    bus.pumps = {}
    bus.redis = type("Redis", (), {"pubsub": lambda _: sub, "aclose": AsyncMock()})()
    queue = await bus.subscribe()
    await bus.unsubscribe(queue)


@asynccontextmanager
async def servers(archive_factory=None, audio_archive_factory=None):
    credentials = {DEVICE: {"device_token_sha256": hashlib.sha256(DEVICE_KEY.encode()).hexdigest(),
                            "app_token_sha256": hashlib.sha256(APP_KEY.encode()).hexdigest()}}
    bus = MemoryBus()
    running = []
    for _ in range(2):
        sock = socket.socket(); sock.bind(("127.0.0.1", 0)); sock.listen(); sock.setblocking(False)
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(Settings(credentials, rpc_timeout=0.25), bus, archive=archive_factory() if archive_factory else None, audio_archive=audio_archive_factory() if audio_archive_factory else None),
                                log_level="critical", ws_max_size=16384))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            if task.done():
                task.result()
            await asyncio.sleep(0.01)
        running.append((server, task, sock, port))
    try:
        yield running[0][3], running[1][3]
    finally:
        for server, *_ in running:
            server.should_exit = True
        await asyncio.gather(*(item[1] for item in running))
        for _, _, sock, _ in running:
            sock.close()


def packet(kind=1, age=0, sent_delay=0):
    if kind == 1:
        payload = struct.pack("<6I", 0x32524452, 1000, age, 1, 0, 0)
    else:
        payload = struct.pack("<5I", 0x32445541, 1, 16000, 320, 0) + b"\0" * 640
    return struct.pack("<6IQ", 0x31505443, kind, 1, 1, 1000, len(payload),
                       int(time.time() * 1000 - sent_delay)) + payload


@pytest.mark.asyncio
async def test_cross_instance_radar_and_authentication():
    async with servers() as (a, b):
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{a}") as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/openapi.json")).status_code == 404
            assert (await client.get(PREFIX + "/api/status")).status_code == 401
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link", additional_headers=AUTH):
                pass  # An app token must never impersonate its PCB.
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer " + DEVICE_KEY}) as device:
            async with connect(f"ws://127.0.0.1:{b}{PREFIX}/ws", additional_headers=AUTH) as phone:
                await device.send(packet(sent_delay=25))
                await asyncio.sleep(0.03)
                await phone.send("next3")
                data = await phone.recv()
                assert isinstance(data, bytes) and data[:4] == b"RDR2"
                assert 25 <= struct.unpack_from("<I", data, 8)[0] < 350
                await phone.send("next3")
                assert await phone.recv() == "waiting"  # No duplicate observations.
            # Reject a second connection, even when it hits another instance.
            with pytest.raises(InvalidStatus):
                async with connect(f"ws://127.0.0.1:{b}{PREFIX}/link",
                                   additional_headers={"Authorization": "Bearer " + DEVICE_KEY}):
                    pass


@pytest.mark.asyncio
async def test_radar_receipt_ack_and_ingest_metrics_cross_instance():
    async with servers() as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer " + DEVICE_KEY}) as pcb:
            await pcb.send(packet())
            ack = json.loads(await asyncio.wait_for(pcb.recv(), 1))
            assert ack == {"kind": "radar_ack", "boot": 1, "seq": 1, "stamp": 1000}
            second = bytearray(packet()); struct.pack_into("<I", second, 12, 2)
            struct.pack_into("<I", second, 44, 3)
            await pcb.send(second)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as phone:
                assert (await phone.get(PREFIX+"/ingest/status")).status_code == 401
                for _ in range(100):
                    r = await phone.get(PREFIX+"/ingest/status", headers=AUTH)
                    if (r.json().get("latest") or {}).get("sequence") == 2:
                        break
                    await asyncio.sleep(.01)
                j = r.json()
                assert j["latest"]["frame_index"] == 3 and j["latest"]["frames_received"] == 2
                assert j["latest"]["frame_gaps"] == 1
                assert j["recent_frames"] == 2 and j["last_received_age_ms"] < 1000


@pytest.mark.asyncio
async def test_ota_routes_require_app_auth_and_preserve_manifest():
    async with servers() as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer " + DEVICE_KEY}) as device:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as app:
                manifest = {"url":"https://storage.googleapis.com/citra-ai-events/firmware/test.bin",
                            "sha256":"0" * 64}
                assert (await app.post(PREFIX + "/api/ota", json=manifest)).status_code == 401
                assert (await app.get(PREFIX + "/api/ota")).status_code == 401
                update = asyncio.create_task(app.post(PREFIX + "/api/ota", json=manifest, headers=AUTH))
                command = json.loads(await device.recv())
                assert command["method"] == "POST" and command["path"] == "/api/ota"
                assert json.loads(base64.b64decode(command["body"])) == manifest
                await device.send(json.dumps({"kind":"response","id":command["id"],"status":202,
                    "body":base64.b64encode(b'{"accepted":true}').decode()}))
                response = await update
                assert response.status_code == 202 and response.json()["accepted"]
                assert response.headers["content-type"].startswith("application/json")
                status = asyncio.create_task(app.get(PREFIX + "/api/ota", headers=AUTH))
                command = json.loads(await device.recv())
                assert command["path"] == "/api/ota" and command["method"] == "GET"
                await device.send(json.dumps({"kind":"response","id":command["id"],"status":200,
                    "body":base64.b64encode(b'{"running_partition":"ota_0"}').decode()}))
                assert (await status).json()["running_partition"] == "ota_0"
                assert (await app.post(PREFIX + "/api/ota", content=b'x' * 4097, headers=AUTH)).status_code == 413



@pytest.mark.asyncio
async def test_cross_instance_binary_audio_rpc_and_whitelist():
    async with servers() as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer " + DEVICE_KEY}) as device:
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as phone:
                pcm = struct.pack("<4h", -32768, -1, 0, 32767)
                upload = asyncio.create_task(phone.post(PREFIX + "/call/pcm", content=pcm,
                         headers={**AUTH, "X-Call-Token": "b" * 32}))
                command = json.loads(await device.recv())
                assert command["method"] == "POST" and command["path"] == "/call/pcm"
                assert base64.b64decode(command["body"]) == pcm
                assert command["call_token"] == "b" * 32
                await device.send(json.dumps({"kind": "response", "id": command["id"], "status": 200,
                                              "body": base64.b64encode(b"OK").decode()}))
                assert (await upload).content == b"OK"
                download = asyncio.create_task(phone.get(PREFIX + "/call/pcm?after=7", headers={**AUTH, "X-Call-Token": "b" * 32}))
                command = json.loads(await device.recv())
                assert command["method"] == "GET" and command["path"] == "/call/pcm?after=7"
                recording = struct.pack("<5I", 0x32445541, 8, 16000, 320, 0) + struct.pack("<320h", *([-3210, 1234] * 160))
                await device.send(json.dumps({"kind": "response", "id": command["id"], "status": 200,
                                              "body": base64.b64encode(recording).decode()}))
                assert (await download).content == recording
                health = asyncio.create_task(phone.get(PREFIX + "/api/status", headers=AUTH))
                command = json.loads(await device.recv())
                assert command["path"] == "/api/status"
                await device.send(json.dumps({"kind": "response", "id": command["id"], "status": 200,
                      "body": base64.b64encode(b'{"frames":55,"age_ms":20,"environment":{"model":"BME690"}}').decode()}))
                assert (await health).json()["environment"]["model"] == "BME690"
                assert (await phone.get(PREFIX + "/api/status")).status_code == 401
                assert (await phone.get(PREFIX + "/../../metadata", headers=AUTH)).status_code in (401, 404)
                assert (await phone.post(PREFIX + "/call/pcm", headers=AUTH, content=b"x" * 4097)).status_code == 413
                assert (await phone.get(PREFIX + "/call/pcm?after=-1", headers=AUTH)).status_code == 400
                assert (await phone.get(PREFIX + "/call/pcm", headers=AUTH)).status_code == 403


@pytest.mark.asyncio
async def test_no_replay_of_stale_radar_and_offline_timeout():
    async with servers() as (a, b):
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",
                           additional_headers={"Authorization": "Bearer " + DEVICE_KEY}) as device:
            await device.send(packet(age=400))
            await device.send(packet(kind=2))  # Continuous mic transport uses its own packet kind.
            await asyncio.sleep(0.03)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as client:
                live = await client.get(PREFIX + "/audio/live", headers=AUTH)
                assert live.content[:4] == b"AUD2" and len(live.content) == 660
                assert (await client.get(PREFIX + "/audio/live")).status_code == 401
            async with connect(f"ws://127.0.0.1:{b}{PREFIX}/ws", additional_headers=AUTH) as phone:
                await phone.send("next3")
                assert await phone.recv() == "waiting"
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as phone:
            assert (await phone.get(PREFIX + "/api/status", headers=AUTH)).status_code == 504


@pytest.mark.asyncio
async def test_production_refuses_ram_only_routing():
    app = create_app(Settings({}))
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_production_refuses_plaintext_redis():
    app = create_app(Settings({}, redis_url="redis://localhost:6379"))
    with pytest.raises(RuntimeError, match="verified TLS"):
        async with app.router.lifespan_context(app):
            pass


def test_cannot_disable_redis_certificate_verification():
    with pytest.raises(RuntimeError, match="certificate verification"):
        RedisBus("rediss://redis.example:6379?ssl_cert_reqs=none")

@pytest.mark.asyncio
async def test_independent_audio_link_preserves_radar_owner_and_rejects_wrong_role():
    """Audio failure/close must not take ownership of the radar command link."""
    from websockets.exceptions import ConnectionClosed
    headers = {"Authorization": "Bearer " + DEVICE_KEY}
    async with servers() as (a, b):
        with pytest.raises(InvalidStatus):
            async with connect(f"ws://127.0.0.1:{a}{PREFIX}/audio-link", additional_headers=AUTH):
                pass
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link", additional_headers=headers) as radar:
            async with connect(f"ws://127.0.0.1:{b}{PREFIX}/audio-link", additional_headers=headers) as audio:
                # Duplicate audio is denied without affecting the primary socket.
                with pytest.raises(InvalidStatus):
                    async with connect(f"ws://127.0.0.1:{a}{PREFIX}/audio-link", additional_headers=headers):
                        pass
                await audio.send(packet(2))
                await radar.send(packet())
                ack = json.loads(await asyncio.wait_for(radar.recv(), 1))
                assert ack["kind"] == "radar_ack"
                await asyncio.sleep(.04)
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{a}") as client:
                    live = await client.get(PREFIX + "/audio/live", headers=AUTH)
                    assert live.status_code == 200 and live.content[:4] == b"AUD2"
                # Audio route cannot inject radar or command responses.
                await audio.send(packet())
                with pytest.raises(ConnectionClosed):
                    await audio.recv()
            second = bytearray(packet());struct.pack_into("<I", second, 12, 2)
            await radar.send(second)
            await asyncio.sleep(.04)
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as client:
                status = (await client.get(PREFIX + "/ingest/status", headers=AUTH)).json()
                assert status["latest"]["sequence"] == 2

@pytest.mark.asyncio
async def test_split_links_archive_both_streams_without_audio_losing_radar():
    from radar_archive import RadarArchive
    from audio_archive import AudioArchive
    class Writer:
        def __init__(self): self.objects=[]
        def write(self, name, data, metadata):
            self.objects.append((name, data, metadata));return "1"
    radar_writer, audio_writer = Writer(), Writer()
    async with servers(
        archive_factory=lambda: RadarArchive(bucket="test", writer=radar_writer, flush_seconds=.05),
        audio_archive_factory=lambda: AudioArchive(bucket="test", writer=audio_writer, blocks_per_clip=5),
    ) as (a, b):
        headers={"Authorization":"Bearer "+DEVICE_KEY}
        async with connect(f"ws://127.0.0.1:{a}{PREFIX}/link",additional_headers=headers) as radar:
            async with connect(f"ws://127.0.0.1:{b}{PREFIX}/audio-link",additional_headers=headers) as audio:
                for i in range(5):
                    rp=bytearray(packet());struct.pack_into("<I",rp,12,i+1);struct.pack_into("<I",rp,44,i+1)
                    ap=bytearray(packet(2));struct.pack_into("<I",ap,12,i+1);struct.pack_into("<I",ap,16,1000+i*20);struct.pack_into("<I",ap,36,i+1)
                    await asyncio.gather(radar.send(rp),audio.send(ap))
                ack=json.loads(await asyncio.wait_for(radar.recv(),1));assert ack['kind']=='radar_ack'
                for _ in range(50):
                    if audio_writer.objects and radar_writer.objects:break
                    await asyncio.sleep(.02)
                assert audio_writer.objects and radar_writer.objects
                import wave,io,gzip
                with wave.open(io.BytesIO(audio_writer.objects[0][1])) as wav:
                    assert wav.getnframes()==1600 and wav.getframerate()==16000
                assert sum(len(gzip.decompress(data).splitlines()) for _,data,_ in radar_writer.objects)==5
                async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{b}") as client:
                    state=(await client.get(PREFIX+'/audio/archive/status',headers=AUTH)).json()
                    assert state['instance_metrics']['missing_blocks']==0
                    assert state['instance_metrics']['queue_dropped']==0
