#!/usr/bin/env python3
"""Bounded silent duplex call test; records counters, never microphone content.

Refuses an active call, verifies a five-second playback gap survives while the
amplifier mutes, then runs simultaneous microphone, speaker and radar traffic.
"""
import argparse, asyncio, json, struct, time
from pathlib import Path
import httpx
from websockets.asyncio.client import connect

async def main(args):
    pair=json.loads(Path('.cloud-local/pairing.json').read_text())
    origin='https://citraverse-pcb-route-avebsk4vna-el.a.run.app'
    base='/v1/devices/'+pair['device_id']; headers={'Authorization':'Bearer '+pair['app_token']}
    report={'seconds':args.seconds,'uploads':0,'mic_batches':0,'radar_frames':0,'errors':[],'upload_ms':[]}
    async with httpx.AsyncClient(base_url=origin,headers=headers,timeout=15) as c:
        async def status(path):
            r=await c.get(base+path);r.raise_for_status();return r.json()
        report['before']=await status('/api/power')
        report['cloud_before']=await status('/api/status')
        if report['before'].get('call_active'):raise RuntimeError('Existing call left untouched')
        r=await c.post(base+'/call/start',content=b'');r.raise_for_status();token={'X-Call-Token':r.json()['token']}
        tasks=[]
        try:
            r=await c.post(base+'/call/pcm',headers=token,content=bytes(3200));r.raise_for_status()
            await asyncio.sleep(5)
            report['gap']=await status('/api/power')
            r=await c.post(base+'/call/pcm',headers=token,content=bytes(3200));report['gap_resume_status']=r.status_code;r.raise_for_status()
            end=time.monotonic()+args.seconds
            async def speaker():
                while time.monotonic()<end:
                    start=time.monotonic()
                    try:
                        r=await c.post(base+'/call/pcm',headers=token,content=bytes(3200));r.raise_for_status()
                        report['uploads']+=1;report['upload_ms'].append(round(1000*(time.monotonic()-start)))
                    except Exception as e:report['errors'].append('speaker:'+type(e).__name__)
                    await asyncio.sleep(max(0,.1-(time.monotonic()-start)))
            async def mic():
                seq=0
                while time.monotonic()<end:
                    try:
                        r=await c.get(base+'/audio/live',params={'after':seq});r.raise_for_status()
                        if r.status_code==204:continue
                        magic,first,rate,samples,errors=struct.unpack_from('<5I',r.content)
                        assert magic==0x32445541 and rate==16000 and len(r.content)==20+samples*2
                        seq=(first+samples//320-1)&0xffffffff;report['mic_batches']+=1
                    except Exception as e:report['errors'].append('mic:'+type(e).__name__)
                    await asyncio.sleep(.03)
            async def radar():
                async with connect(origin.replace('https://','wss://')+base+'/ws',additional_headers=headers) as ws:
                    last=None;report['radar_index_misses']=0
                    while time.monotonic()<end:
                        await ws.send('next3');data=await asyncio.wait_for(ws.recv(),5)
                        if isinstance(data,str):continue
                        offset=0
                        while offset<len(data):
                            magic,_,age,index,words,frag=struct.unpack_from('<6I',data,offset)
                            assert magic==0x32524452 and offset+24+words*4<=len(data)
                            if last is not None:report['radar_index_misses']+=max(0,((index-last)&0xffffffff)-1)
                            last=index;report['radar_frames']+=1;offset+=24+words*4
            tasks=[asyncio.create_task(f()) for f in (speaker,mic,radar)]
            await asyncio.gather(*tasks)
            report['during']=await status('/api/power')
        finally:
            for task in tasks:
                if not task.done():task.cancel()
            r=await c.post(base+'/call/stop',headers=token,content=b'');report['hangup_status']=r.status_code
        await asyncio.sleep(.2)
        report['after']=await status('/api/power');report['cloud_after']=await status('/api/status')
    times=sorted(report.pop('upload_ms'));report['upload_p95_ms']=times[int(.95*(len(times)-1))] if times else None
    report['passed']=bool(not report['errors'] and report['uploads']>args.seconds*5 and report['mic_batches']>args.seconds*5 and report['gap']['call_active'] and not report['gap']['amp_level'] and report['gap_resume_status']==200 and report['hangup_status']==200 and not report['after']['call_active'] and not report['after']['amp_level'] and report['after']['tx_errors']==report['before']['tx_errors'])
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','uploads','mic_batches','radar_frames','radar_index_misses','upload_p95_ms','errors','hangup_status')},indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=90);p.add_argument('--output',required=True);a=p.parse_args()
    if not 30<=a.seconds<=180:raise ValueError('Use 30–180 seconds')
    asyncio.run(main(a))
