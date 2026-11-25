#!/usr/bin/env python3
"""Offline replay of completed overnight segments. No network or credentials."""
import collections,gzip,json,math,pathlib,struct,statistics
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def frames(data):
 off=0
 while off<len(data):
  magic,ts,age,idx,words,frag=struct.unpack_from('<6I',data,off);end=off+24+4*words
  if magic!=0x32524452 or frag or end>len(data):raise ValueError('Invalid frame')
  p=off+24;pts=[]
  while p<end:
   kind,flags,n=struct.unpack_from('<BBH',data,p);p+=4
   if kind!=4 or flags>3 or n%12 or p+n>end:raise ValueError('Invalid TLV')
   if flags&1:
    for k in range(p,p+n,12):
     x,y,z,v,snr,_=struct.unpack_from('<hhhhHH',data,k)
     x,y,z=x/100,y/100,z/100;x,z=-x,-z;t=math.radians(10);y,z=y*math.cos(t)+z*math.sin(t),z*math.cos(t)-y*math.sin(t);h=math.radians(135)
     pts.append((x*math.cos(h)+y*math.sin(h)-1.35,-x*math.sin(h)+y*math.cos(h)+2.85,z+2,v/100,snr/100,bool(flags&2)))
   p+=n
  yield age,pts;off=end

def grouped(points,radius,dimensions=2):
 # Grid-based connected components; same single-link structure as dashboard.
 n=len(points);parent=list(range(n));grid=collections.defaultdict(list)
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 for i,p in enumerate(points):
  cell=tuple(math.floor(p[k]/radius) for k in range(dimensions))
  import itertools
  for delta in itertools.product([-1,0,1],repeat=dimensions):
   neighbor=tuple(cell[k]+delta[k] for k in range(dimensions))
   for j in grid[neighbor]:
    if sum((p[k]-points[j][k])**2 for k in range(dimensions))<=radius**2:parent[find(i)]=find(j)
  grid[cell].append(i)
 groups=collections.defaultdict(list)
 for i in range(n):groups[find(i)].append(points[i])
 return list(groups.values())
def density_groups(points,radius,min_samples):
 # DBSCAN: only dense cores connect components; sparse bridges cannot merge them.
 grid=collections.defaultdict(list)
 for i,p in enumerate(points):grid[(math.floor(p[0]/radius),math.floor(p[1]/radius))].append(i)
 neighbors=[]
 for p in points:
  cx,cy=math.floor(p[0]/radius),math.floor(p[1]/radius);ns=[]
  for dx in [-1,0,1]:
   for dy in [-1,0,1]:
    for j in grid[(cx+dx,cy+dy)]:
     if (p[0]-points[j][0])**2+(p[1]-points[j][1])**2<=radius**2:ns.append(j)
  neighbors.append(ns)
 core={i for i,ns in enumerate(neighbors) if len(ns)>=min_samples};labels={};groups=[]
 for seed in sorted(core):
  if seed in labels:continue
  label=len(groups);groups.append([]);queue=[seed];labels[seed]=label
  for i in queue:
   groups[label].append(i)
   for j in neighbors[i]:
    if j in core and j not in labels:labels[j]=label;queue.append(j)
 for i,p in enumerate(points):
  if i in core:continue
  candidates=[j for j in neighbors[i] if j in core]
  if candidates:
   j=min(candidates,key=lambda j:(p[0]-points[j][0])**2+(p[1]-points[j][1])**2);groups[labels[j]].append(i)
 return [[points[i] for i in g] for g in groups]

def segment_replay(seg):
 file=OUT/(seg['segment']+'.rdr.gz');lastsecond=None;counts=collections.Counter();sampled=0;nearbed=collections.Counter()
 with gzip.open(file,'rb') as f:
  while header:=f.read(12):
   epoch,size=struct.unpack('<dI',header);data=f.read(size)
   if len(data)!=size:raise ValueError('Truncated raw capture')
   if int(epoch)==lastsecond:continue
   lastsecond=int(epoch)
   for age,pts in frames(data):
    if age>350:continue
    sampled+=1
    # Bed strict footprint and expanded default footprint; broad right half is sensitivity only.
    strict=[p for p in pts if .35<=p[0]<=1.35 and .85<=p[1]<=2.85 and .25<=p[2]<=1.65]
    bed=[p for p in pts if .15<=p[0]<=1.5 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
    broad=[p for p in pts if 0<=p[0]<=1.5 and .5<=p[1]<=3 and .2<=p[2]<=1.8]
    
    for width in [1,1.5,1.8,2]:
     left=1.35-width;mid=1.35-width/2
     zone=[p for p in pts if left-.2<=p[0]<=1.5 and .65<=p[1]<=3 and .25<=p[2]<=1.65]
     nearbed[f'width_{width}_present']+=len(zone)>=3
     nearbed[f'width_{width}_both_halves']+=sum(p[0]<mid for p in zone)>=3 and sum(p[0]>=mid for p in zone)>=3
    room=[p for p in pts if -1.5<=p[0]<=1.5 and 0<=p[1]<=3 and -.15<=p[2]<=3]
    n3=len([g for g in grouped(room,.65,3) if len(g)>=6])
    counts['room3d-zero']+=n3==0;counts['room3d-one']+=n3==1;counts['room3d-two']+=n3==2;counts['room3d-many']+=n3>2
    nearbed['strict_present']+=len(strict)>=3;nearbed['expanded_present']+=len(bed)>=3;nearbed['broad_present']+=len(broad)>=3
    for snr in [0,20,24,27,30,33]:
     selected=[p for p in bed if p[4]>=snr or (p[4]==0 and len(p)>5 and p[5])]
     for radius in [.2,.3,.4]:
      for method in ['link','density']:
       groups=grouped(selected,radius) if method=='link' else density_groups(selected,radius,6)
       g=[g for g in groups if len(g)>=6];n=len(g);prefix=f'snr{snr}-{method}{radius}'
       counts[prefix+'-zero']+=n==0;counts[prefix+'-one']+=n==1;counts[prefix+'-two']+=n==2;counts[prefix+'-many']+=n>2
    for radius in [.2,.3,.4,.5,.65]:
     for support in [4,6]:
      dg=density_groups(bed,radius,support);n=len([g for g in dg if len(g)>=6]);prefix=f'db{radius}-core{support}'
      counts[prefix+'-zero']+=n==0;counts[prefix+'-one']+=n==1;counts[prefix+'-two']+=n==2;counts[prefix+'-many']+=n>2
     groups=grouped(bed,radius)
     for minimum in [3,6]:
      g=[g for g in groups if len(g)>=minimum];n=len(g);prefix=f'r{radius}-min{minimum}'
      counts[prefix+'-zero']+=n==0;counts[prefix+'-one']+=n==1;counts[prefix+'-two']+=n==2;counts[prefix+'-many']+=n>2
      if n==2:
       c=[(statistics.mean(p[0] for p in a),statistics.mean(p[1] for p in a)) for a in g]
       counts[prefix+'-separated_two']+=math.dist(c[0],c[1])>=.35
    break
 return {'segment':seg['segment'],'sampled_seconds':sampled,'zone_presence_fractions':{k:v/max(1,sampled) for k,v in nearbed.items()},'cluster_fractions':{k:v/max(1,sampled) for k,v in counts.items()}}
def main():
 segments=[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))];replays=[]
 cachefile=OUT/'replay-analysis.json';cached=json.loads(cachefile.read_text()) if cachefile.exists() else {};cache={r['segment']:r for r in cached.get('segments',[])} if cached.get('version')==4 else {}
 for seg in segments:
  r=cache.get(seg['segment']) or segment_replay(seg);replays.append(r);print(seg['segment'],r['sampled_seconds'],flush=True)
 cachefile.write_text(json.dumps({'version':4,'segments':replays,'warning':'Two spatial clusters are not proof of two people; default bed dimensions unconfirmed.'},indent=2))
 grouped_profiles=collections.defaultdict(list)
 for s in segments:grouped_profiles[json.dumps(s['profile'],sort_keys=True)].append(s)
 summary=[]
 for profile,ss in grouped_profiles.items():
  duration=sum(s['duration_s'] for s in ss);n=sum(s['counts'].get('fresh',0) for s in ss)
  summary.append({'profile':json.loads(profile),'labels':[s['label'] for s in ss],'segments':len(ss),'duration_minutes':duration/60,'fresh_frames':n,'fresh_fps':n/max(1,duration),'bed_presence_fraction':sum(s['counts'].get('bed_present',0) for s in ss)/max(1,n),'both_halves_fraction':sum(s['counts'].get('both_halves',0) for s in ss)/max(1,n),'outside_point_fraction':sum(s['counts'].get('outside_points',0) for s in ss)/max(1,sum(s['counts'].get('outside_points',0)+s['counts'].get('bed_points',0) for s in ss)),'proxy_score_mean':statistics.mean(s['proxy_score'] for s in ss),'segment_score_min':min(s['proxy_score'] for s in ss),'segment_score_max':max(s['proxy_score'] for s in ss),'age_p95_segment_max':max(s['age_p95_ms'] or 0 for s in ss),'outages_over_500ms':sum(s['outages_over_500ms'] for s in ss)})
 summary.sort(key=lambda x:x['proxy_score_mean'],reverse=True)
 (OUT/'profile-summary.json').write_text(json.dumps({'profiles':summary,'segments':len(segments),'scope':'Best observed stability among tested profiles; person-count accuracy is unverified.'},indent=2))
if __name__=='__main__':main()
