"""Audit fresh stationary-seat evidence in every captured presence frame."""
import argparse, gzip, json, math
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('capture',type=Path)
p.add_argument('--x',type=float,default=-.2402809604)
p.add_argument('--y',type=float,default=1.025518486)
p.add_argument('--seconds',type=float,default=302)
a=p.parse_args()
text=gzip.open(a.capture,'rt',encoding='utf-8').read() if a.capture.suffix=='.gz' else a.capture.read_text()
rows=[]
for line in text.splitlines():
 try: rows.append(json.loads(line))
 except ValueError: pass  # Live last line may still be being written.
if not rows: raise SystemExit('No captured frames')
start=rows[0]['time_s']
rows=[r for r in rows if r['time_s']-start<=a.seconds]
result=dict(frames=len(rows),duration_s=rows[-1]['time_s']-start,anchor=[a.x,a.y],radius_m=.5,snr_min=18,raw_presence_points=sum(len(r['points']) for r in rows),modes={})
for sparse in (False,True):
 last=None; accepted=[]; fresh=0; visible=0; rejected=[]
 for r in rows:
  t=r['time_s']; points=r['points']
  inside=[q for q in points if all(math.isfinite(q.get(k,float('nan'))) for k in ('x','y','z','snr')) and (q['x']-a.x)**2+(q['y']-a.y)**2<=.5**2]
  n=len({tuple(round(q[k],2) for k in ('x','y','z')) for q in inside if q['snr']>=18})
  required=2 if sparse and last is not None and 0<=t-last<=.5 else 3
  if n>=required:
   last=t; accepted.append(t)
  elif points:
   rejected.append(dict(elapsed_s=round(t-start,3),qualified=n,inside=len(inside),total=len(points)))
  age=t-last if last is not None else float('inf')
  fresh+=age<=.35
  visible+=age<=2
 gaps=[dict(start_s=round(x-start,3),end_s=round(y-start,3),duration_s=round(y-x,3)) for x,y in zip(accepted,accepted[1:]) if y-x>.35]
 result['modes']['sparse_continuation' if sparse else 'three_point_baseline']=dict(accepted_bursts=len(accepted),fresh_frames=fresh,visible_frames=visible,missing_frames=len(rows)-visible,max_internal_evidence_gap_s=max((y-x for x,y in zip(accepted,accepted[1:])),default=None),tail_evidence_age_s=rows[-1]['time_s']-last if last is not None else None,gaps_over_350ms=gaps,rejected_nonempty_bursts=rejected)
out=a.capture.with_name(a.capture.name.split('.')[0]+'_audit_summary.json')
out.write_text(json.dumps(result,indent=2)+'\n')
for k,v in result['modes'].items():print(k,{x:y for x,y in v.items() if not isinstance(y,list)})
print('duration_s',result['duration_s'],'frames',result['frames'])
