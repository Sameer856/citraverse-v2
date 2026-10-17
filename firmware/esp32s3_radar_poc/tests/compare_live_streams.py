import http.client,struct,time,json,threading,websocket
import argparse
p=argparse.ArgumentParser()
p.add_argument('--host',required=True)
p.add_argument('--baseline-seconds',type=int,default=30)
p.add_argument('--combined-seconds',type=int,default=120)
p.add_argument('--reserve-ms',type=int,default=1600)
a=p.parse_args()
HOST=a.host
def health():
 c=http.client.HTTPConnection(HOST,timeout=3);c.request('GET','/api/status');v=json.loads(c.getresponse().read());c.close();return v
def run(seconds,audio):
 s={'audio':audio,'radar_frames':0,'radar_gaps':0,'audio_blocks':0,'audio_gaps':0,'audio_read_errors':0,'simulated_playback_underruns':0};before=health();start=time.monotonic();end=start+seconds
 def radar():
  last=None
  try:
   w=websocket.create_connection('ws://'+HOST+'/ws',timeout=3)
   while time.monotonic()<end:
    w.send('next3');b=w.recv()
    if not isinstance(b,bytes):time.sleep(.005);continue
    offset=0
    while offset<len(b):
     magic,stamp,age,index,words,reserved=struct.unpack_from('<6I',b,offset)
     assert magic==0x32524452 and reserved==0
     if last is not None:s['radar_gaps']+=(index-last-1)&0xffffffff
     last=index;s['radar_frames']+=1;offset+=24+words*4
    assert offset==len(b)
   w.close()
  except Exception as e:s['radar_error']=str(e)
 t=threading.Thread(target=radar);t.start()
 if audio:
  c=websocket.create_connection('ws://'+HOST+':81/ws',timeout=3);after=0;next_play=0
  candidates={ms:{'next':0,'underruns':0} for ms in [100,200,300,500,800,1000,1200,1600]}
  last_audio=None;max_gap=0
  try:
   while time.monotonic()<end:
    c.send('next '+str(after)+' 0');b=c.recv()
    magic,first,rate,n,errors=struct.unpack_from('<5I',b)
    assert magic==0x32445541 and rate==16000 and len(b)==20+2*n and n<=1600
    if n:
     if after:s['audio_gaps']+=(first-after-1)&0xffffffff
     after=first+n//320-1;s['audio_blocks']+=n//320;s['audio_read_errors']=errors
     now=time.monotonic()
     if next_play<now:
      if next_play:s['simulated_playback_underruns']+=1
      next_play=now+a.reserve_ms/1000
     next_play+=n/rate
     if last_audio is not None:max_gap=max(max_gap,now-last_audio)
     last_audio=now
     for ms,v in candidates.items():
      if v['next']<now:
       if v['next']:v['underruns']+=1
       v['next']=now+ms/1000
      v['next']+=n/rate

  except Exception as e:s['audio_error']=str(e)
  c.close()
  s['reserve_ms']=a.reserve_ms;s['max_audio_arrival_gap_ms']=round(max_gap*1000,1)
  s['candidate_underruns']={ms:v['underruns'] for ms,v in candidates.items()}
 else:
  while time.monotonic()<end:time.sleep(.1)
 t.join();elapsed=time.monotonic()-start
 try:after=health()
 except Exception as e:
  s.update(seconds=elapsed,status_error=str(e));print(json.dumps(s),flush=True);return s
 s.update(seconds=elapsed,acquisition_fps=(after['frames']-before['frames'])/elapsed,viewer_fps=s['radar_frames']/elapsed,copy_drops=after['viewer_copy_drops']-before['viewer_copy_drops'],free_heap=after['free_heap'])
 print(json.dumps(s),flush=True);return s
if __name__ == '__main__':
 results=[run(a.baseline_seconds,False),run(a.combined_seconds,True)]
 assert all(not any(k.endswith('_error') for k in r) for r in results), 'Connection failed'
 assert all(r['radar_gaps']==0 and r['copy_drops']==0 for r in results), 'Radar dropped frames'
 assert results[1]['audio_gaps']==0 and results[1]['audio_read_errors']==0, 'Audio dropped blocks'
 assert results[1]['simulated_playback_underruns']==0, 'Playback reserve exhausted'
 assert results[1]['acquisition_fps']>=results[0]['acquisition_fps']*.98, 'Radar FPS regressed'
