#!/usr/bin/env python3
"""Bounded read-only dual-stream soak; no keys or PCM in report output."""
import argparse,asyncio,json,pathlib,struct,time,statistics
import httpx
from websockets.asyncio.client import connect
from inspect_archive import inspect as inspect_radar
from inspect_audio import inspect as inspect_audio

async def main(args):
    pair=json.loads(pathlib.Path(args.pairing).read_text())
    prefix='/v1/devices/'+pair['device_id'];headers={'Authorization':'Bearer '+pair['app_token']}
    out=pathlib.Path(args.output);out.mkdir(parents=True,exist_ok=True)
    report={'started_epoch_ms':int(time.time()*1000),'seconds_requested':args.seconds}
    async with httpx.AsyncClient(base_url=args.origin,headers=headers,timeout=20) as c:
        async def snapshot():
            result={}
            for name,path in [('pcb','/api/status'),('ota','/api/ota'),('radar','/archive/status'),('audio','/audio/archive/status'),('ingest','/ingest/status')]:
                r=await c.get(prefix+path);r.raise_for_status();result[name]=r.json()
            return result
        report['before']=await snapshot()
        end=time.monotonic()+args.seconds;ages=[];frames=0;missing=0;last=None;times=[];audio_blocks=0;audio_missing=0;audio_last=None;audio_peaks=[]
        async def radar():
            nonlocal frames,missing,last
            async with connect(args.origin.replace('https://','wss://')+prefix+'/ws',additional_headers=headers) as ws:
                while time.monotonic()<end:
                    await ws.send('next3');data=await asyncio.wait_for(ws.recv(),10)
                    if isinstance(data,str):continue
                    off=0
                    while off<len(data):
                        magic,stamp,age,index,words,frag=struct.unpack_from('<6I',data,off)
                        size=24+words*4
                        if magic!=0x32524452 or off+size>len(data):raise ValueError('Invalid radar packet')
                        if last is not None:missing+=max(0,((index-last)&0xffffffff)-1)
                        last=index;frames+=1;ages.append(age);times.append(time.monotonic());off+=size
        async def audio():
            nonlocal audio_blocks,audio_missing,audio_last
            while time.monotonic()<end:
                r=await c.get(prefix+'/audio/live',params={'after':audio_last or 0});r.raise_for_status();b=r.content
                magic,seq,rate,samples,errors=struct.unpack_from('<5I',b)
                if magic!=0x32445541 or rate!=16000 or len(b)!=20+2*samples or samples%320:raise ValueError('Invalid audio packet')
                if samples:
                    if audio_last is not None:audio_missing+=max(0,((seq-audio_last)&0xffffffff)-1)
                    audio_last=(seq+samples//320-1)&0xffffffff;audio_blocks+=samples//320
                    pcm=struct.unpack_from('<'+'h'*samples,b,20);audio_peaks.append(max(abs(x) for x in pcm))
                await asyncio.sleep(.03)
        await asyncio.gather(radar(),audio())
        report['after']=await snapshot()
        report['live']={'radar_frames':frames,'radar_fps':(frames-1)/(times[-1]-times[0]) if len(times)>1 else 0,'radar_index_misses':missing,'radar_age_p95_ms':sorted(ages)[int((len(ages)-1)*.95)] if ages else None,'radar_max_receive_gap_ms':max((b-a)*1000 for a,b in zip(times,times[1:])) if len(times)>1 else None,'audio_blocks_received':audio_blocks,'audio_live_cursor_misses':audio_missing,'audio_peak_max':max(audio_peaks,default=0),'note':'HTTP live cursor misses may be viewer-side; compare archive missing_blocks separately.'}
        report['objects']={}
        for name,inspect in [('radar',inspect_radar),('audio',inspect_audio)]:
            commit=report['after'][name]['latest_commit']
            if not commit or commit['committed_epoch_ms']<report['started_epoch_ms']:raise ValueError('No new '+name+' GCS commit')
            url='https://storage.googleapis.com/'+commit['bucket']+'/'+commit['object_name'];r=await c.get(url,headers={'Authorization':''});r.raise_for_status()
            file=out/('verified.wav' if name=='audio' else 'verified.jsonl.gz');file.write_bytes(r.content)
            report['objects'][name]=inspect(file,commit['sha256'])
            report['objects'][name]['commit']=commit
        report['counter_deltas']={}
        for group in ['cloud','storage']:
            a,b=report['before']['pcb'][group],report['after']['pcb'][group]
            report['counter_deltas'][group]={k:b[k]-a[k] for k in a if isinstance(a[k],int) and not isinstance(a[k],bool) and isinstance(b.get(k),int)}
        report['qualified_zero_drop_soak']=bool(
            report['live']['radar_fps']>=18 and report['live']['radar_index_misses']==0
            and report['live']['radar_age_p95_ms']<=350
            and all(report['counter_deltas']['cloud'].get(k,0)==0 for k in ['dropped','reconnects','send_failures','queue_drops','stale_drops','audio_dropped','audio_reconnects','audio_send_failures'])
            and report['objects']['audio']['duration_seconds']==30
            and report['objects']['audio']['commit'].get('missing_blocks',-1)==0
            and not report['objects']['audio']['commit'].get('partial',True))
        report['ended_epoch_ms']=int(time.time()*1000)
        (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'live':report['live'],'objects':report['objects']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',default='https://citraverse-pcb-route-avebsk4vna-el.a.run.app');p.add_argument('--pairing',default='.cloud-local/pairing.json');p.add_argument('--seconds',type=int,default=120);p.add_argument('--output',required=True);args=p.parse_args()
    if not 30<=args.seconds<=600:p.error('seconds must be between 30 and 600')
    asyncio.run(main(args))
