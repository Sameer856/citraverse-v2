#!/usr/bin/env python3
"""Play a short, low-level GCP speaker test and verify hang-up mute.

Requires --play-tone explicitly. Never prints the call/device credentials.
A successful I2S counter test does not prove the physical speaker is audible.
"""
import argparse
import asyncio
import json
import math
from pathlib import Path
import struct
import time
import httpx
from websockets.asyncio.client import connect

async def main(args):
    if not args.play_tone:raise ValueError('Pass --play-tone to send sound to the PCB')
    pair=json.loads(Path(args.pairing).read_text());prefix='/v1/devices/'+pair['device_id']
    headers={'Authorization':'Bearer '+pair['app_token']}
    report={'speaker_acoustic_confirmation':None,'tone_seconds':args.duration,'tone_peak_pcm16':args.peak}
    async with httpx.AsyncClient(base_url=args.origin,headers=headers,timeout=15) as client:
        async def get(path):
            response=await client.get(prefix+path);response.raise_for_status();return response.json()
        report['before']=await get('/api/power')
        report['radar_before']=await get('/api/status')
        if report['before'].get('call_active'):raise RuntimeError('An existing call is active; left it untouched')
        response=await client.post(prefix+'/call/start',content=b'');response.raise_for_status();call=response.json()
        token={'X-Call-Token':call['token']}
        frames=[];reader=None
        async def observe_radar():
            async with connect(args.origin.replace('https://','wss://')+prefix+'/ws',additional_headers=headers) as ws:
                until=time.monotonic()+args.duration+1.2
                while time.monotonic()<until:
                    await ws.send('next3');data=await asyncio.wait_for(ws.recv(),5)
                    if isinstance(data,str):continue
                    offset=0
                    while offset<len(data):
                        magic,_,age,index,words,frag=struct.unpack_from('<6I',data,offset)
                        size=24+words*4
                        if magic!=0x32524452 or offset+size>len(data):raise ValueError('Invalid radar payload')
                        frames.append((time.monotonic(),index,age));offset+=size
        try:
            reader=asyncio.create_task(observe_radar())
            start=time.monotonic()
            for block in range(round(args.duration*10)):
                await asyncio.sleep(max(0,start+block*.1-time.monotonic()))
                samples=[]
                for i in range(1600):
                    n=block*1600+i;edge=min(1,n/160,(round(args.duration*16000)-1-n)/160)
                    samples.append(round(args.peak*max(0,edge)*math.sin(2*math.pi*660*n/16000)))
                response=await client.post(prefix+'/call/pcm',headers=token,content=struct.pack('<1600h',*samples))
                response.raise_for_status()
            await asyncio.sleep(.2)
            response=await client.get(prefix+'/audio/live');response.raise_for_status()
            magic,seq,rate,samples,errors=struct.unpack_from('<5I',response.content)
            report['microphone_route']='/audio/live'
            report['call_microphone']={'valid':magic==0x32445541 and rate==16000 and len(response.content)==20+samples*2,'samples':samples,'read_errors':errors}
            report['during']=await get('/api/power')
            await reader
        finally:
            # Explicit hang-up, even after a failed upload. The PCB also has a
            # three-second idle lease as a fallback if the network disappears.
            response=await client.post(prefix+'/call/stop',headers=token,content=b'')
            report['hangup_http_status']=response.status_code
            if reader and not reader.done():reader.cancel()
        await asyncio.sleep(.15)
        report['after']=await get('/api/power');report['radar_after']=await get('/api/status')
    report['speaker_deltas']={k:report['during'][k]-report['before'][k] for k in ['tx_accepted','tx_audible','tx_errors']}
    report['amp_during']=report['during']['amp_level'];report['amp_after']=report['after']['amp_level']
    report['radar_frames_during_test']=len(frames)
    report['radar_index_misses']=sum(max(0,((b[1]-a[1])&0xffffffff)-1) for a,b in zip(frames,frames[1:]))
    report['transport_verified']=bool(report['speaker_deltas']['tx_accepted']==round(args.duration*50) and report['speaker_deltas']['tx_audible']==round(args.duration*50) and report['speaker_deltas']['tx_errors']==0 and report['call_microphone']['valid'] and not report['after']['call_active'] and report['after']['amp_level']==0 and len(frames)>=40)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['speaker_deltas','amp_during','amp_after','radar_frames_during_test','radar_index_misses','call_microphone','transport_verified']},indent=2))
    if not report['transport_verified']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--play-tone',action='store_true',required=True);p.add_argument('--duration',type=float,choices=[.5,1.,2.],default=.5);p.add_argument('--peak',type=int,choices=[4000,12000,16000],default=4000);p.add_argument('--pairing',default='.cloud-local/pairing.json');p.add_argument('--origin',default='https://citraverse-pcb-route-avebsk4vna-el.a.run.app');p.add_argument('--output',required=True);asyncio.run(main(p.parse_args()))
