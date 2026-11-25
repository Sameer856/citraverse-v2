#!/usr/bin/env python3
"""Descriptive return maps only; never selects parameters or contacts a device."""
import gzip,hashlib,json,math,pathlib,struct
import analyze
OUT=analyze.OUT
N=30
def sample_cells(points):
 return {(min(N-1,int((p[0]+1.5)/.1)),min(N-1,int(p[1]/.1))) for p in points if all(math.isfinite(v) for v in p[:3]) and -1.5<=p[0]<=1.5 and 0<=p[1]<=3 and .25<=p[2]<=1.65}
def segment_map(segment):
 counts=[0]*(N*N);samples=0;lastsecond=None
 with gzip.open(OUT/(segment+'.rdr.gz'),'rb') as file:
  while header:=file.read(12):
   if len(header)!=12:raise ValueError('Truncated map record')
   epoch,size=struct.unpack('<dI',header);payload=file.read(size)
   if len(payload)!=size:raise ValueError('Truncated map payload')
   if int(epoch)==lastsecond:continue
   for age,points in analyze.frames(payload):
    if age>350:continue
    lastsecond=int(epoch);samples+=1
    for x,y in sample_cells(points):counts[y*N+x]+=1
    break
 assert all(0<=v<=samples for v in counts)
 return {'segment':segment,'sampled_frames':samples,'counts':counts}
def main():
 choice=json.loads((OUT/'final-method-selection.json').read_text()) if (OUT/'final-method-selection.json').exists() else {}
 summaries=[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))]
 names={s['segment'] for s in summaries}
 groups=[('baseline_reference','Baseline reference',['011-baseline-overnight-observation']),('alternate_observed','Alternate: observed repeats',['013-crossover-static0-first','014-crossover-static0-repeat']),('final_observation','Final independent observation',[s['segment'] for s in summaries if s['started_epoch']>=choice.get('frozen_epoch',float('inf')) and s['profile']==choice.get('selected_profile')])]
 target=OUT/'return-map-analysis.json';source_hash=hashlib.sha256(pathlib.Path(__file__).read_bytes()+pathlib.Path(analyze.__file__).read_bytes()).hexdigest()
 old=json.loads(target.read_text()) if target.exists() else {}
 cached={s['segment']:s for s in old.get('segments',[])} if old.get('source_hash')==source_hash else {}
 used={name for _,_,selected in groups for name in selected if name in names};records={name:cached.get(name) or segment_map(name) for name in sorted(used)};panels=[]
 for key,label,selected in groups:
  rows=[records[name] for name in selected if name in records];samples=sum(r['sampled_frames'] for r in rows);counts=[sum(r['counts'][i] for r in rows) for i in range(N*N)]
  panels.append({'key':key,'label':label,'segments':[r['segment'] for r in rows],'sampled_frames':samples,'cell_frame_fractions':[v/max(1,samples) for v in counts]})
 result={'version':1,'source_hash':source_hash,'grid':{'columns':N,'rows':N,'cell_m':.1,'x_min':-1.5,'y_min':0,'z_min':.25,'z_max':1.65},'segments':list(records.values()),'panels':panels,'interpretation':'One fresh frame per receive-second. Each cell shows the fraction of sampled frames containing at least one return at 0.25–1.65 m world height; repeated points in a frame do not add support. Same world transform and 1 m assumed bed as the frozen analysis. Descriptive only: no person labels, no occupancy probability, no post-holdout fitting. The aborted crossover cannot establish a causal improvement.'}
 temp=target.with_suffix('.tmp');temp.write_text(json.dumps(result));temp.replace(target);print('Return maps:',[(p['key'],p['sampled_frames']) for p in panels],flush=True)
if __name__=='__main__':main()
