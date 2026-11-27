#!/usr/bin/env python3
"""Measure real-time half-duplex delivery; send silence, retain counters only."""
import argparse,asyncio,json,struct,time
from pathlib import Path
import httpx
from websockets.asyncio.client import connect

async def main(args):
    pair=json.loads(Path('.cloud-local/pairing.json').read_text());prefix='/v1/devices/'+pair['device_id']
    headers={'Authorization':'Bearer '+pair['app_token']};base=args.origin+prefix
    report={'seconds':args.seconds,'sent':0,'accepted_samples':0,'capture_skips':0,'ack_errors':[],
            'heartbeat_errors':[],'telemetry_errors':[],'telemetry_requests':0,'diagnostic_retries':0,'radar_frames':0,'radar_index_misses':0,'rtt_ms':[]}
    async with httpx.AsyncClient(headers=headers,timeout=10) as c:
        async def power():
            for attempt in range(3):
                r=await c.get(base+'/api/power')
                if r.status_code in (502,503,504) and attempt<2:report['diagnostic_retries']+=1;continue
                r.raise_for_status();return r.json()
        report['before']=await power()
        if report['before']['call_active']:raise RuntimeError('Existing call left untouched')
        r=await c.post(base+'/call/start');r.raise_for_status();token={'X-Call-Token':r.json()['token']}
        stop=asyncio.Event();tasks=[];pending={};done=False
        async def heartbeat():
            while not stop.is_set():
                try:await asyncio.wait_for(stop.wait(),5);return
                except asyncio.TimeoutError:pass
                r=await c.get(base+'/call/pcm',headers=token)
                if r.status_code!=200:report['heartbeat_errors'].append(r.status_code)
        async def telemetry():
            while not stop.is_set():
                r=await c.get(base+'/api/status')
                report['telemetry_requests']+=1
                if r.status_code!=200:report['telemetry_errors'].append(r.status_code)
                try:await asyncio.wait_for(stop.wait(),1)
                except asyncio.TimeoutError:pass
        async def radar():
            async with connect(args.origin.replace('https://','wss://')+prefix+'/ws',additional_headers=headers,compression=None) as ws:
                last=None
                while not stop.is_set():
                    await ws.send('next3');data=await asyncio.wait_for(ws.recv(),5)
                    if isinstance(data,str):continue
                    offset=0
                    while offset<len(data):
                        magic,_,age,index,words,frag=struct.unpack_from('<6I',data,offset)
                        assert magic==0x32524452 and offset+24+words*4<=len(data)
                        if last is not None:report['radar_index_misses']+=max(0,((index-last)&0xffffffff)-1)
                        last=index;report['radar_frames']+=1;offset+=24+words*4
        try:
            tasks=[asyncio.create_task(heartbeat()),asyncio.create_task(radar()),asyncio.create_task(telemetry())]
            async with connect(args.origin.replace('https://','wss://')+prefix+'/call/stream',additional_headers={**headers,**token},compression=None) as ws:
                ready=json.loads(await asyncio.wait_for(ws.recv(),6))
                assert ready.get('kind')=='ready' and ready['max_inflight']==4
                async def acks():
                    while not done or pending:
                        try:ack=json.loads(await asyncio.wait_for(ws.recv(),.5))
                        except asyncio.TimeoutError:
                            if done and not pending:return
                            continue
                        seq=ack['sequence'];stamp=pending.pop(seq)
                        report['rtt_ms'].append(round(1000*(time.monotonic()-stamp)))
                        if ack['status']!=200:report['ack_errors'].append({'sequence':seq,'status':ack['status']})
                        report['accepted_samples']+=ack.get('accepted_samples',0)
                reader=asyncio.create_task(acks());start=time.monotonic();sequence=0;during=None
                try:
                    for frame in range(round(args.seconds/.12)):
                        await asyncio.sleep(max(0,start+frame*.12-time.monotonic()))
                        if len(pending)>=4:report['capture_skips']+=1;continue
                        sequence+=1;pending[sequence]=time.monotonic()
                        await ws.send(struct.pack('<2I',0x31545450,sequence)+bytes(3840));report['sent']+=1
                        if frame==round(args.seconds/.24):during=asyncio.create_task(power())
                    done=True;await asyncio.wait_for(reader,6)
                    if during:report['during']=await during
                finally:
                    done=True
                    if not reader.done():reader.cancel()
            await asyncio.sleep(.6)
            report['after_talk']=await power()
            # Listening alone must keep its lease without enabling speaker output.
            r=await c.get(base+'/call/pcm',headers=token);r.raise_for_status()
            await asyncio.sleep(3.2);report['after_listen']=await power()
        finally:
            stop.set()
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            r=await c.post(base+'/call/stop',headers=token);report['hangup_status']=r.status_code
        await asyncio.sleep(.2);report['after']=await power()
    times=sorted(report.pop('rtt_ms'));report['ack_p95_ms']=times[int(.95*(len(times)-1))] if times else None
    report['played_blocks']=report['after_talk']['tx_audible']-report['before']['tx_audible']
    report['total_starvations']=report['after_talk'].get('tx_starvations',0)-report['before'].get('tx_starvations',0)
    report['during_starvations']=report.get('during',{}).get('tx_starvations',0)-report['before'].get('tx_starvations',0)
    report['passed']=bool(not report['ack_errors'] and not report['capture_skips'] and not report['heartbeat_errors'] and not report['telemetry_errors'] and
        report['played_blocks']==report['sent']*6 and report['accepted_samples']==report['sent']*1920 and
        report['total_starvations']=report['after_talk'].get('tx_starvations',0)-report['before'].get('tx_starvations',0)
    report['during_starvations']==0 and report['total_starvations']<=1 and report['after']['tx_errors']==report['before']['tx_errors'] and
        report['hangup_status']==200 and not report['after']['call_active'] and not report['after_listen']['amp_level'])
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','sent','capture_skips','ack_errors','heartbeat_errors','telemetry_errors','telemetry_requests','diagnostic_retries','ack_p95_ms','played_blocks','during_starvations','total_starvations','radar_frames','radar_index_misses')},indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',default='https://citraverse-pcb-route-avebsk4vna-el.a.run.app');p.add_argument('--seconds',type=int,default=60);p.add_argument('--output',required=True);asyncio.run(main(p.parse_args()))
