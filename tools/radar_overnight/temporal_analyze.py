#!/usr/bin/env python3
"""Test short evidence accumulation without treating stale boxes as fresh people."""
import collections,gzip,json,struct,math
import analyze as a
try:
 import numpy as np
except ImportError:np=None

def unique_points(history,now,window):
 voxels={}
 for when,points in history:
  if when<now-window:continue
  for p in points:
   key=(math.floor((p[0]+1e-9)/.04),math.floor((p[1]+1e-9)/.04))
   voxels[key]=(*p,when)
 return list(voxels.values())
def anisotropic_groups(points,across,along):
 # Elliptical distance in bed X/Y coordinates; no target-count constraint.
 if not points:return []
 if np is None:
  scaled=[(p[0]/across,p[1]/along,*p[2:]) for p in points]
  return [[(p[0]*across,p[1]*along,*p[2:]) for p in g] for g in a.grouped(scaled,1)]
 xy=np.asarray([(p[0]/across,p[1]/along) for p in points]);delta=xy[:,None,:]-xy[None,:,:];edges=np.sum(delta*delta,axis=2)<=1
 used=np.zeros(len(points),dtype=bool);groups=[]
 for seed in range(len(points)):
  if used[seed]:continue
  queue=[seed];used[seed]=True
  for i in queue:
   new=np.flatnonzero(edges[i]&~used);used[new]=True;queue.extend(new.tolist())
   if used.all():break
  groups.append([points[i] for i in queue])
 return groups
def measure(history,now,window,radius,minimum):
 points=unique_points(history,now,window);groups=[g for g in a.grouped(points,radius) if len(g)>=minimum]
 recent=[g for g in groups if sum(p[-1]>=now-.2 for p in g)>=3]
 return len(groups),len(recent)
def replay(seg):
 history=collections.deque();last=None;laststamp=None;second=None;counts=collections.Counter();samples=0
 with gzip.open(a.OUT/(seg['segment']+'.rdr.gz'),'rb') as f:
  while header:=f.read(12):
   now,size=struct.unpack('<dI',header);payload=f.read(size)
   if len(payload)!=size:raise ValueError('Truncated capture')
   if last is not None and now-last>.5:history.clear()
   last=now
   for stamp,age,index,points in a.frames(payload,True):
    sensor_now=stamp/1000
    if laststamp is not None and sensor_now<=laststamp:history.clear()
    laststamp=sensor_now
    if age>350:history.clear();continue
    bed=[p for p in points if .15<=p[0]<=1.5 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
    history.append((sensor_now,bed))
    while history and history[0][0]<sensor_now-1:history.popleft()
    if int(now)==second:continue
    second=int(now);samples+=1
    for window in [.2,.5,1.0]:
     selected=unique_points(history,sensor_now,window)
     for radius in [.2,.3,.4]:
      groups=a.grouped(selected,radius)
      for minimum in [3,6]:
       g=[g for g in groups if len(g)>=minimum];n=len(g);fresh=sum(sum(p[-1]>=sensor_now-.2 for p in c)>=3 for c in g);prefix=f'w{window}-r{radius}-min{minimum}'
       counts[prefix+'-two_any']+=n==2;counts[prefix+'-two_recent']+=fresh==2;counts[prefix+'-many_recent']+=fresh>2;counts[prefix+'-one_recent']+=fresh==1;counts[prefix+'-zero_recent']+=fresh==0
     for across in [.15,.2,.25,.3]:
      for along in [.6,1.0,1.4]:
       groups=anisotropic_groups(selected,across,along)
       for minimum in [3,6]:
        g=[g for g in groups if len(g)>=minimum];n=len(g);fresh=sum(sum(p[-1]>=sensor_now-.2 for p in c)>=3 for c in g);prefix=f'a{window}-x{across}-y{along}-min{minimum}'
        counts[prefix+'-two_any']+=n==2;counts[prefix+'-two_recent']+=fresh==2;counts[prefix+'-many_recent']+=fresh>2;counts[prefix+'-one_recent']+=fresh==1;counts[prefix+'-zero_recent']+=fresh==0

 return {'segment':seg['segment'],'sampled_seconds':samples,'fractions':{k:v/max(1,samples) for k,v in counts.items()}}
def main():
 path=a.OUT/'temporal-analysis.json';old=json.loads(path.read_text()) if path.exists() else {};cache={s['segment']:s for s in old.get('segments',[])} if old.get('version')==5 else {};results=[]
 for file in sorted(a.OUT.glob('segment-*.json')):
  seg=json.loads(file.read_text());result=cache.get(seg['segment']) or replay(seg);results.append(result);print('temporal',seg['segment'],result['sampled_seconds'],flush=True)
 temp=path.with_suffix('.tmp');temp.write_text(json.dumps({'version':5,'segments':results,'definition':'Sensor-frame clock; unique 4 cm XY voxels; at least three distinct voxels updated within 200 ms to call a group recent. Historical-only groups are not counted as fresh detections.','limitation':'No person identity or ground truth inferred.'},indent=2));temp.replace(path)
if __name__=='__main__':main()
