#!/usr/bin/env python3
"""Test walkie-talkie call phases without saving microphone content."""
import asyncio,json,struct,time,argparse
from pathlib import Path
import httpx

async def main(output):
    pair=json.loads(Path('.cloud-local/pairing.json').read_text())
    base='https://citraverse-pcb-route-avebsk4vna-el.a.run.app/v1/devices/'+pair['device_id']
    report={'errors':[],'listen_batches':0,'talk_uploads':0,'diagnostic_retries':0}
    async with httpx.AsyncClient(headers={'Authorization':'Bearer '+pair['app_token']},timeout=12) as c:
        async def power():
            for attempt in range(3):
                r=await c.get(base+'/api/power')
                if r.status_code in (502,503,504) and attempt<2:
                    report['diagnostic_retries']+=1
                    continue
                r.raise_for_status();return r.json()
        report['before']=await power()
        if report['before']['call_active']:raise RuntimeError('Existing call left untouched')
        r=await c.post(base+'/call/start');r.raise_for_status();token={'X-Call-Token':r.json()['token']}
        async def listen(seconds):
            end=time.monotonic()+seconds;next_keep=0;seq=0
            while time.monotonic()<end:
                if time.monotonic()>=next_keep:
                    r=await c.get(base+'/call/pcm',headers=token);r.raise_for_status();next_keep=time.monotonic()+5
                r=await c.get(base+'/audio/live',params={'after':seq});r.raise_for_status()
                magic,first,rate,samples,errors=struct.unpack_from('<5I',r.content)
                assert magic==0x32445541 and rate==16000 and len(r.content)==20+samples*2
                if samples:seq=(first+samples//320-1)&0xffffffff;report['listen_batches']+=1
                await asyncio.sleep(.05)
        try:
            await listen(25);report['after_long_listen']=await power()
            end=time.monotonic()+8
            while time.monotonic()<end:
                start=time.monotonic();r=await c.post(base+'/call/pcm',headers=token,content=bytes(3840));r.raise_for_status()
                report['talk_uploads']+=1
                await asyncio.sleep(max(0,.12-(time.monotonic()-start)))
            report['after_talk']=await power()
            await listen(5);report['after_listen']=await power()
        finally:
            r=await c.post(base+'/call/stop',headers=token);report['hangup_status']=r.status_code
        await asyncio.sleep(.2);report['after']=await power()
    report['passed']=bool(report['after_long_listen']['call_active'] and not report['after_long_listen']['amp_level'] and report['after_talk']['call_active'] and report['after_talk']['tx_gain_q16']==65536 and report['after_listen']['call_active'] and not report['after_listen']['amp_level'] and report['after']['tx_errors']==report['before']['tx_errors'] and not report['after']['call_active'] and report['hangup_status']==200)
    Path(output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('passed','listen_batches','talk_uploads','hangup_status')}))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True);asyncio.run(main(p.parse_args().output))
