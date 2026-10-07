"""Read-only HTTP/WebSocket smoke/soak check for the Wi-Fi radar host."""
import argparse,json,struct,time,urllib.request,sys
from pathlib import Path
import websocket
sys.path.insert(0,str(Path(__file__).resolve().parent))
from parse_example import cartesian_points
p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--seconds',type=float,default=60);p.add_argument('--output',required=True);a=p.parse_args()
def status():return json.load(urllib.request.urlopen('http://'+a.host+'/api/status',timeout=5))
page=urllib.request.urlopen('http://'+a.host+'/',timeout=5).read()
assert b'Citraverse / Radar' in page
before=status();s=websocket.create_connection('ws://'+a.host+'/ws',timeout=5)
start=time.monotonic();indices=[];frames=0;point_count=0;largest=0;duplicates=0;gaps=0;error=None
try:
 while time.monotonic()-start<a.seconds:
  tick=time.monotonic();s.send('next');data=s.recv()
  if isinstance(data,bytes):
   assert 12<=len(data)<=8192
   idx,words,offset=struct.unpack_from('<III',data)
   assert offset==0 and words*4==len(data)-12
   points=cartesian_points(data[12:]);frames+=1;point_count+=len(points);largest=max(largest,len(data))
   if indices:
    delta=(idx-indices[-1])&0xffffffff
    if delta==0:duplicates+=1
    elif delta!=1:gaps+=delta-1
   indices.append(idx)
  time.sleep(max(0,.05-(time.monotonic()-tick)))
except Exception as exc:
 error=type(exc).__name__+": "+str(exc)
finally:s.close()
elapsed=time.monotonic()-start
try:after=status()
except Exception as exc:after={"error":type(exc).__name__+": "+str(exc)}
result={'error':error,'elapsed_seconds':elapsed,'binary_messages':frames,'unique_frames':len(set(indices)),'unique_fps':len(set(indices))/elapsed,'duplicate_snapshots':duplicates,'skipped_preview_indices':gaps,'points_decoded':point_count,'largest_callback_bytes':largest,'status_before':before,'status_after':after,'first_index':indices[0] if indices else None,'last_index':indices[-1] if indices else None}
Path(a.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
