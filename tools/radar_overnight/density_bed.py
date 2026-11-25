#!/usr/bin/env python3
"""Exploratory bed-aligned DBSCAN. No hardware writes; never constrains target count."""
import collections,gzip,json,struct,itertools
import numpy as np
import analyze as a
from temporal_analyze import unique_points
DEVELOPMENT=['000-baseline','003-baseline-repeat','008-baseline-overnight-observation','009-baseline-overnight-observation']

def density_groups(points,across,along,core_minimum):
 if not points:return []
 xy=np.asarray([(p[0]/across,p[1]/along) for p in points]);delta=xy[:,None,:]-xy[None,:,:];dist=np.sum(delta*delta,axis=2);edge=dist<=1
 core=edge.sum(axis=1)>=core_minimum;labels=np.full(len(points),-1,dtype=int);groups=[]
 for seed in np.flatnonzero(core):
  if labels[seed]>=0:continue
  label=len(groups);queue=[int(seed)];labels[seed]=label
  for i in queue:
   new=np.flatnonzero(edge[i]&core&(labels<0));labels[new]=label;queue.extend(new.tolist())
  groups.append(queue)
 for i in np.flatnonzero(~core):
  choices=np.flatnonzero(edge[i]&core)
  if len(choices):
   nearest=choices[np.argmin(dist[i,choices])];groups[labels[nearest]].append(int(i))
 return [[points[i] for i in group] for group in groups]

def replay(seg):
 history=collections.deque();last=None;laststamp=None;second=None;counts=collections.Counter();samples=0
 with gzip.open(a.OUT/(seg['segment']+'.rdr.gz'),'rb') as f:
  while header:=f.read(12):
   epoch,size=struct.unpack('<dI',header);payload=f.read(size)
   if len(payload)!=size:raise ValueError('Truncated capture')
   if last is not None and epoch-last>.5:history.clear()
   last=epoch
   for stamp,age,index,points in a.frames(payload,True):
    now=stamp/1000
    if laststamp is not None and (now<=laststamp or now-laststamp>.35):history.clear()
    laststamp=now
    if age>350:history.clear();continue
    bed=[p for p in points if .15<=p[0]<=1.5 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
    history.append((now,bed))
    while history and history[0][0]<now-1:history.popleft()
    if int(epoch)==second:continue
    second=int(epoch);samples+=1
    for window in [.2,.5,1.0]:
     selected=unique_points(history,now,window)
     for across,along,core in itertools.product([.12,.15,.2,.25],[.8,1.,1.4],[3,4,6]):
      groups=density_groups(selected,across,along,core)
      for minimum in [3,6]:
       qualifying=[g for g in groups if len(g)>=minimum];fresh=sum(sum(p[-1]>=now-.2 for p in g)>=3 for g in qualifying)
       prefix=f'd{window}-x{across}-y{along}-core{core}-min{minimum}'
       for key,value in [('zero',fresh==0),('one',fresh==1),('two',fresh==2),('many',fresh>2),('weak',any(sum(p[-1]>=now-.2 for p in g)<3 for g in qualifying))]:counts[prefix+'-'+key]+=value
 return {'segment':seg['segment'],'samples':samples,'fractions':{k:v/max(1,samples) for k,v in counts.items()}}
def main():
 target=a.OUT/'density-bed-development.json';prior=json.loads(target.read_text()) if target.exists() else {};cache={s['segment']:s for s in prior.get('segments',[])} if prior.get('version')==1 else {};results=[]
 for name in DEVELOPMENT:
  seg=json.loads((a.OUT/('segment-'+name+'.json')).read_text());r=cache.get(name) or replay(seg);results.append(r);print('density',name,r['samples'],flush=True)
  temp=target.with_suffix('.tmp');temp.write_text(json.dumps({'version':1,'development_only':True,'segments':results},indent=2));temp.replace(target)
 keys={k[:-4] for r in results for k in r['fractions'] if k.endswith('-two')};rank=[]
 for method in keys:
  two=[r['fractions'].get(method+'-two',0) for r in results];many=[r['fractions'].get(method+'-many',0) for r in results];zero=[r['fractions'].get(method+'-zero',0) for r in results]
  rank.append({'method':method,'two':two,'many':many,'zero':zero,'score':min(two)+.25*sum(two)/len(two)-.5*max(many)-.5*max(zero)})
 rank.sort(key=lambda r:r['score'],reverse=True);(a.OUT/'density-bed-ranking.json').write_text(json.dumps({'development_segments':DEVELOPMENT,'selection_score':'min(two) + 0.25 mean(two) - 0.5 max(many) - 0.5 max(zero); unverified spatial proxy, not accuracy','candidates':rank},indent=2));print(json.dumps(rank[:5],indent=2))
if __name__=='__main__':main()
