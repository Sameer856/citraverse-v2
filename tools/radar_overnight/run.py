#!/usr/bin/env python3
"""Bounded radar-only comparison. Never writes NVS or firmware; preserves baseline."""
import asyncio, collections, datetime as dt, gzip, json, math, pathlib, statistics, struct, time, uuid
import httpx
from websockets.asyncio.client import connect
ROOT=pathlib.Path(__file__).resolve().parents[2]
OUT=ROOT/'output/radar_overnight_20261125'; OUT.mkdir(parents=True,exist_ok=True)
PAIR=json.loads((ROOT/'.cloud-local/pairing.json').read_text())
ORIGIN='https://citraverse-pcb-route-avebsk4vna-el.a.run.app'
PREFIX='/v1/devices/'+PAIR['device_id']; HEAD={'Authorization':'Bearer '+PAIR['app_token']}
TZ=dt.timezone(dt.timedelta(hours=5,minutes=30))
END=dt.datetime(2026,11,26,7,0,tzinfo=TZ).timestamp()
MOUNT={'width':3,'depth':3,'height':2,'roll':180,'tilt':10,'corner':'far-left','inset':.15,'heading':135}
BED={'width':1,'length':2,'height':.55,'inset':.15,'dimensions_confirmed':False}
BASE=None

def stamp():return dt.datetime.now(TZ).isoformat()
def dump(path,value):
 p=OUT/path;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,indent=2));t.replace(p)
def event(kind,**data):
 with (OUT/'events.jsonl').open('a') as f:f.write(json.dumps({'time':stamp(),'event':kind,**data})+'\n')
 print(stamp(),kind,json.dumps(data),flush=True)
def quant(a,q):return sorted(a)[min(len(a)-1,int((len(a)-1)*q))] if a else None

def decode(data):
 off=0
 while off<len(data):
  if off+24>len(data):raise ValueError('short header')
  magic,ts,age,idx,words,frag=struct.unpack_from('<6I',data,off);end=off+24+4*words
  if magic!=0x32524452 or words>2048 or frag or end>len(data):raise ValueError('invalid frame')
  p=off+24;pts=[];polar=0
  while p<end:
   if p+4>end:raise ValueError('short TLV')
   kind,flags,n=struct.unpack_from('<BBH',data,p);p+=4
   if kind!=4 or flags>3 or n%12 or p+n>end:raise ValueError('invalid TLV')
   if flags&1:
    for k in range(p,p+n,12):
     x,y,z,v,snr,_=struct.unpack_from('<hhhhHH',data,k);pts.append((x/100,y/100,z/100,v/100,snr/100,bool(flags&2)))
   else:polar+=n//12
   p+=n
  yield ts,age,idx,pts,polar;off=end

def world(p):
 x,y,z,v,snr,presence=p
 # 180 roll, 10 degree down tilt, 135 degree clockwise heading.
 x,z=-x,-z;t=math.radians(10);y,z=y*math.cos(t)+z*math.sin(t),z*math.cos(t)-y*math.sin(t)
 h=math.radians(135)
 return x*math.cos(h)+y*math.sin(h)-1.35,-x*math.sin(h)+y*math.cos(h)+2.85,z+2,v,snr,presence

def features(points):
 valid=[world(p) for p in points];room=[p for p in valid if -1.5<=p[0]<=1.5 and 0<=p[1]<=3 and -.15<=p[2]<=3]
 # Default bed: x=.35..1.35, y=.85..2.85, with 20 cm spatial margin.
 bed=[p for p in room if .15<=p[0]<=1.55 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
 left=sum(p[0]<.85 for p in bed);right=len(bed)-left
 return {'raw':len(points),'room':len(room),'bed':len(bed),'left':left,'right':right,'outside':len(room)-len(bed),'slow_bed':sum(abs(p[3])<=.1 for p in bed),'presence_bed':sum(p[5] for p in bed),'bed_top':quant([p[2] for p in bed],.9)}

async def rpc(client,action='status',**extra):
 body={'operation':'radar_tuning','action':action,**extra}
 r=await client.post(PREFIX+'/api/ota',json=body,headers=HEAD);r.raise_for_status();return r.json()
async def health(client):
 r=await client.get(PREFIX+'/api/status',headers=HEAD);r.raise_for_status();return r.json()
async def apply(client,profile,label):
 before=await rpc(client)
 if before['busy']:raise RuntimeError('another tuning operation is active')
 rid=str(uuid.uuid4());event('apply',label=label,request_id=rid,profile=profile)
 try:await rpc(client,'apply',profile=profile,request_id=rid)
 except (httpx.TimeoutException,httpx.NetworkError):event('apply_reply_delayed',request_id=rid)
 until=time.monotonic()+100
 while time.monotonic()<until:
  await asyncio.sleep(2)
  try:s=await rpc(client)
  except (httpx.HTTPError,ValueError):continue
  if s.get('boot_id')!=before.get('boot_id'):raise RuntimeError('unexpected PCB reboot')
  if s.get('request_id')==rid and not s.get('busy'):
   dump('last_readback.json',s)
   event('readback',label=label,state=s)
   if s.get('error') or not s.get('frames_verified') or not s.get('frames_recent'):raise RuntimeError(s.get('error') or 'fresh frames not confirmed')
   if s.get('active')!=profile:raise RuntimeError('active profile differs from request')
   await asyncio.sleep(10);return s
 raise TimeoutError('profile did not finish in 100 seconds')

async def capture(client,profile,label,seconds):
 start=time.monotonic();wall=time.time();name=f'{len(list(OUT.glob("segment-*.json"))):03d}-{label}'
 counts=collections.Counter();ages=[];bedcounts=[];outside=[];lastidx=None;lastrecv=None;outages=[];last_status=0
 starthealth=await health(client)
 raw=gzip.open(OUT/(name+'.rdr.gz'),'wb');metrics=gzip.open(OUT/(name+'.metrics.jsonl.gz'),'wt')
 event('capture_start',segment=name,seconds=seconds)
 while time.monotonic()-start<seconds and time.time()<END:
  try:
   async with connect(ORIGIN.replace('https:','wss:')+PREFIX+'/ws',additional_headers=HEAD,open_timeout=15,max_size=2**20) as ws:
    while time.monotonic()-start<seconds and time.time()<END:
     await ws.send('next3');data=await asyncio.wait_for(ws.recv(),12);now=time.time()
     if isinstance(data,str):
      counts['waiting']+=1;await asyncio.sleep(.05);continue
     raw.write(struct.pack('<dI',now,len(data))+data)
     for ts,age,idx,pts,polar in decode(data):
      if idx==lastidx:counts['duplicate']+=1;continue
      if lastidx is not None:
       delta=(idx-lastidx)&0xffffffff
       if delta>0x7fffffff:counts['resets']+=1
       elif delta>1:counts['missing_frames']+=delta-1
      lastidx=idx
      if lastrecv and now-lastrecv>.5:outages.append(now-lastrecv)
      lastrecv=now;counts['frames']+=1;ages.append(age)
      if age>350:counts['stale']+=1;continue
      if polar:counts['polar']+=polar
      f=features(pts);counts['fresh']+=1;counts['bed_present']+=f['bed']>=3;counts['both_halves']+=f['left']>=3 and f['right']>=3;counts['bed_points']+=f['bed'];counts['outside_points']+=f['outside'];bedcounts.append(f['bed']);outside.append(f['outside'])
      metrics.write(json.dumps({'epoch':now,'stamp':ts,'index':idx,'age':age,**f})+'\n')
     if now-last_status>60:
      h=await health(client);s=await rpc(client);last_status=now
      dump('progress.json',{'time':stamp(),'segment':name,'elapsed_seconds':time.monotonic()-start,'frames':counts['frames'],'fresh':counts['fresh'],'bed_presence_fraction':counts['bed_present']/max(1,counts['fresh']),'both_half_fraction':counts['both_halves']/max(1,counts['fresh']),'active':s.get('active'),'health':h})
      raw.flush();metrics.flush()
      if s.get('active')!=profile:raise RuntimeError('EXTERNAL_PROFILE_CHANGE')
  except RuntimeError:raise
  except Exception as e:
   counts['connection_errors']+=1;event('capture_connection_error',segment=name,error=str(e)[:160]);await asyncio.sleep(2)
 raw.close();metrics.close();elapsed=time.monotonic()-start
 try:endhealth=await health(client)
 except Exception:endhealth={}
 n=max(1,counts['fresh']);bedfraction=counts['bed_present']/n;half=counts['both_halves']/n
 noise=counts['outside_points']/max(1,counts['outside_points']+counts['bed_points'])
 reliability=min(1,counts['fresh']/max(1,elapsed*1000/profile['frame_ms']))
 # This is a repeatability proxy, not person-count accuracy. Static clutter can score well.
 score=100*(.4*bedfraction+.2*half+.2*(1-noise)+.2*reliability)
 result={'label':label,'segment':name,'profile':profile,'started_epoch':wall,'ended_epoch':time.time(),'duration_s':elapsed,'counts':dict(counts),'fps':counts['frames']/max(1,elapsed),'fresh_fps':counts['fresh']/max(1,elapsed),'bed_presence_fraction':bedfraction,'both_bed_halves_fraction':half,'outside_point_fraction':noise,'bed_points_median':quant(bedcounts,.5),'bed_points_p90':quant(bedcounts,.9),'age_p50_ms':quant(ages,.5),'age_p95_ms':quant(ages,.95),'outages_over_500ms':len(outages),'longest_outage_s':max(outages,default=0),'proxy_score':score,'health_before':starthealth,'health_after':endhealth}
 dump('segment-'+name+'.json',result);event('capture_complete',segment=name,score=round(score,2),fps=round(result['fps'],2),bed_fraction=round(bedfraction,3),both_halves=round(half,3));return result

async def main():
 global BASE
 async with httpx.AsyncClient(base_url=ORIGIN,timeout=20) as client:
  initial=await rpc(client);BASE=initial['active'];dump('baseline.json',initial)
  dump('manifest.json',{'start':stamp(),'planned_end':dt.datetime.fromtimestamp(END,TZ).isoformat(),'mount':MOUNT,'bed':BED,'condition':'User says two people remain in bed most of night. No synchronized ground truth or empty-bed control.','raw_format':'gzip records: little-endian double epoch, uint32 payload length, RDR2 payload','safety':'Temporary radar profiles only; no NVS save, no firmware flashing, no automatic noise estimation with occupied bed.'})
  profiles=[('baseline',BASE),('keep-static-legacy80',{**BASE,'static_rm':0})]
  for db in [18,21,24,27,30]:profiles.append((f'static-dB{db}',{**BASE,'static_rm':0,'cfar_value':db,'cfar_method':0}))
  profiles.extend([('baseline-repeat',BASE),('clutter-control',{**BASE,'static_rm':0,'cfar_value':24,'cfar_method':0,'clutter_rm':1}),('slow-speed-fine',{**BASE,'static_rm':0,'cfar_value':24,'cfar_method':0,'speed_mm_s':1600,'speed_step_mm_s':100}),('period100',{**BASE,'static_rm':0,'cfar_value':24,'cfar_method':0,'frame_ms':100}),('method1-dB24',{**BASE,'static_rm':0,'cfar_value':24,'cfar_method':1}),('method2-dB24',{**BASE,'static_rm':0,'cfar_value':24,'cfar_method':2}),('freq57000',{**BASE,'frequency':57000,'static_rm':0,'cfar_value':24,'cfar_method':0}),('range3200',{**BASE,'range_mm':3200,'static_rm':0,'cfar_value':24,'cfar_method':0}),('baseline-final-screen',BASE)])
  results=[];failures=[]
  try:
   for label,p in profiles:
    if time.time()>END-1800:break
    try:
     if (await rpc(client)).get('active')!=p:await apply(client,p,label)
     results.append(await capture(client,p,label,480))
    except RuntimeError as e:
     if str(e)=='EXTERNAL_PROFILE_CHANGE':event('stopped_external_change');return
     failures.append({'label':label,'error':str(e)});event('profile_failed',label=label,error=str(e));await apply(client,BASE,'recovery-baseline')
    except Exception as e:
     failures.append({'label':label,'error':str(e)});event('profile_failed',label=label,error=str(e));await apply(client,BASE,'recovery-baseline')
    dump('comparison.json',{'updated':stamp(),'results':results,'failures':failures})
   good=[r for r in results if r['fresh_fps']>=.8*(1000/r['profile']['frame_ms']) and r['counts'].get('stale',0)<.05*max(1,r['counts']['frames'])]
   top=[]
   for r in sorted(good,key=lambda r:r['proxy_score'],reverse=True):
    if r['profile'] not in [p for _,p in top]:top.append((r['label'],r['profile']))
    if len(top)==3:break
   if not top:top=[('baseline',BASE)]
   dump('shortlist.json',{'candidates':top,'warning':'Ranking uses radar stability/bed-zone proxies, not verified detection of two people.'})
   cycle=0
   while time.time()<END-900:
    label,p=top[cycle%len(top)];cycle+=1
    try:
     await apply(client,p,'repeat-'+label)
     results.append(await capture(client,p,'repeat-'+label,min(1200,max(60,END-time.time()-600))))
    except Exception as e:
     if str(e)=='EXTERNAL_PROFILE_CHANGE':event('stopped_external_change');return
     event('repeat_failed',label=label,error=str(e));await apply(client,BASE,'recovery-baseline')
    dump('comparison.json',{'updated':stamp(),'results':results,'failures':failures})
  finally:
   # Restore the known working profile; keep experimental choices unsaved for review.
   try:await apply(client,BASE,'restore-original-at-end');event('baseline_restored')
   except Exception as e:event('BASELINE_RESTORE_FAILED',error=str(e))
  dump('complete.json',{'time':stamp(),'results':len(results),'baseline_restored':(await rpc(client)).get('active')==BASE})

if __name__=='__main__':
 try:asyncio.run(main())
 except Exception as e:event('FATAL',error=str(e));raise
