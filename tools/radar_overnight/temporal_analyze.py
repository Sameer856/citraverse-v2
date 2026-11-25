#!/usr/bin/env python3
"""Test short evidence accumulation without treating stale boxes as fresh people."""
import collections,gzip,json,struct
import analyze as a

def unique_points(history,now,window):
 voxels={}
 for when,points in history:
  if when<now-window:continue
  for p in points:
   key=(round(p[0]/.04),round(p[1]/.04))
   voxels[key]=(*p,when)
 return list(voxels.values())
def measure(history,now,window,radius,minimum):
 points=unique_points(history,now,window);groups=[g for g in a.grouped(points,radius) if len(g)>=minimum]
 recent=[g for g in groups if sum(p[-1]>=now-.2 for p in g)>=3]
 return len(groups),len(recent)
def replay(seg):
 history=collections.deque();last=None;second=None;counts=collections.Counter();samples=0
 with gzip.open(a.OUT/(seg['segment']+'.rdr.gz'),'rb') as f:
  while header:=f.read(12):
   now,size=struct.unpack('<dI',header);payload=f.read(size)
   if len(payload)!=size:raise ValueError('Truncated capture')
   if last is not None and now-last>.5:history.clear()
   last=now
   for age,points in a.frames(payload):
    if age>350:history.clear();continue
    bed=[p for p in points if .15<=p[0]<=1.5 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
    history.append((now,bed))
    while history and history[0][0]<now-1:history.popleft()
    if int(now)==second:continue
    second=int(now);samples+=1
    for window in [.2,.5,1.0]:
     selected=unique_points(history,now,window)
     for radius in [.2,.3,.4]:
      groups=a.grouped(selected,radius)
      for minimum in [3,6]:
       g=[g for g in groups if len(g)>=minimum];n=len(g);fresh=sum(sum(p[-1]>=now-.2 for p in c)>=3 for c in g);prefix=f'w{window}-r{radius}-min{minimum}'
       counts[prefix+'-two_any']+=n==2;counts[prefix+'-two_recent']+=fresh==2;counts[prefix+'-many_recent']+=fresh>2;counts[prefix+'-one_recent']+=fresh==1;counts[prefix+'-zero_recent']+=fresh==0
 return {'segment':seg['segment'],'sampled_seconds':samples,'fractions':{k:v/max(1,samples) for k,v in counts.items()}}
def main():
 path=a.OUT/'temporal-analysis.json';old=json.loads(path.read_text()) if path.exists() else {};cache={s['segment']:s for s in old.get('segments',[])} if old.get('version')==2 else {};results=[]
 for file in sorted(a.OUT.glob('segment-*.json')):
  seg=json.loads(file.read_text());result=cache.get(seg['segment']) or replay(seg);results.append(result);print('temporal',seg['segment'],result['sampled_seconds'],flush=True)
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'version':2,'segments':results,'definition':'Unique 4 cm XY voxels; at least three distinct voxels updated within 200 ms to call a group recent. Historical-only groups are not counted as fresh detections.','limitation':'No person identity or ground truth inferred.'},indent=2));temp.replace(path)
if __name__=='__main__':main()
