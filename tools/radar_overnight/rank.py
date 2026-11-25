#!/usr/bin/env python3
"""Choose a prospective shortlist; keep repeat observations separate from screening."""
import collections,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def metric_candidates(spatial,temporal):
 f=spatial.get('cluster_fractions',{});result=[]
 for key,value in f.items():
  if key.endswith('-two') and key!='room3d-two':
   prefix=key[:-4];result.append({'method':prefix,'two':value,'many':f.get(prefix+'-many',0),'zero':f.get(prefix+'-zero',0),'window':0})
 result.append({'method':'room3d','two':f.get('room3d-two',0),'many':f.get('room3d-many',0),'zero':f.get('room3d-zero',0),'window':0})
 for key,value in temporal.get('fractions',{}).items():
  if key.endswith('-two_recent'):
   prefix=key[:-11];f2=temporal['fractions'];result.append({'method':prefix,'two':value,'many':f2.get(prefix+'-many_recent',0),'zero':f2.get(prefix+'-zero_recent',0),'window':float(prefix.split('-')[0][1:])})
 return result
def score(m,reliability,bed,fps):
 return 100*(.65*m['two']-.3*m['many']-.1*m['zero']+.15*reliability+.15*bed+.05*min(1,fps/20)-.03*m['window'])
def main():
 spatial={s['segment']:s for s in json.loads((OUT/'replay-analysis.json').read_text())['segments']}
 temporal={s['segment']:s for s in json.loads((OUT/'temporal-analysis.json').read_text())['segments']} if (OUT/'temporal-analysis.json').exists() else {}
 segments=[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))];byprofile=collections.defaultdict(list)
 for s in segments:byprofile[json.dumps(s['profile'],sort_keys=True)].append(s)
 choices=[]
 for key,ss in byprofile.items():
  train=ss[0]
  if train['segment'] not in spatial:continue
  p=train['profile'];reliability=min(1,train['fresh_fps']/(1000/p['frame_ms']))
  if reliability<.8 or p['range_mm']<4000:continue
  metrics=metric_candidates(spatial[train['segment']],temporal.get(train['segment'],{}))
  ranked=sorted(metrics,key=lambda m:score(m,reliability,train['bed_presence_fraction'],train['fresh_fps']),reverse=True)
  best=ranked[0];holdout=[]
  for s in ss[1:]:
   if s['segment'] not in spatial:continue
   match=next((m for m in metric_candidates(spatial[s['segment']],temporal.get(s['segment'],{})) if m['method']==best['method']),None)
   if match:holdout.append({'segment':s['segment'],'label':s['label'],'method':best['method'],'two_group_fraction':match['two'],'many_group_fraction':match['many'],'score':score(match,min(1,s['fresh_fps']/(1000/p['frame_ms'])),s['bed_presence_fraction'],s['fresh_fps'])})
  choices.append({'label':train['label'],'profile':p,'method':best['method'],'training_segment':train['segment'],'training_two_group_fraction':best['two'],'training_many_group_fraction':best['many'],'training_score':score(best,reliability,train['bed_presence_fraction'],train['fresh_fps']),'holdout':holdout,'alternative_methods':ranked[:5]})
 choices.sort(key=lambda x:x['training_score'],reverse=True)
 result={'candidates':choices,'selection_basis':'First completed window for each distinct hardware profile selects its method. Later windows are separately reported holdout; no claim of person-count accuracy.','coverage_gate':'Range at least 4 m, based on approximately 3.66 m slant distance to the assumed bed farthest corner.','screening_only':True}
 tmp=OUT/'candidate-ranking.tmp';tmp.write_text(json.dumps(result,indent=2));tmp.replace(OUT/'candidate-ranking.json')
 for c in choices[:5]:print(c['label'],c['method'],round(c['training_score'],2),flush=True)
if __name__=='__main__':main()
