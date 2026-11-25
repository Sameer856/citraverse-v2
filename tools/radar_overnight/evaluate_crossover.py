#!/usr/bin/env python3
"""Evaluate pre-recorded crossover criteria. Does not configure hardware."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def evaluate(criteria,baseline,segments,methods,completion):
 comparison=criteria['comparison'];before=next((s for s in segments if s['segment']==comparison['baseline_before']),None)
 bylabel={s['label']:s for s in segments};alternate=[bylabel.get(label) for label in comparison['alternate_labels']];after=bylabel.get(comparison['baseline_after_label']);ordered=[before,*alternate,after]
 missing=[name for name,s in zip(['baseline before',*comparison['alternate_labels'],'baseline after'],ordered) if s is None]
 if completion and completion.get('aborted'):
  return {'status':'evaluated','alternate_passed':False,'selected_profile':baseline,'gates':[{'name':'crossover completed without a reboot or abort','passed':False,'actual':'aborted','limit':'complete uninterrupted comparison'}],'missing':missing,'aggregate':{},'segments':[s['segment'] for s in ordered if s is not None],'limitation':criteria['limitation'],'interpretation':'Comparison aborted. Retain the original baseline; partial alternate improvements cannot establish a winner.'}
 if missing or not completion:return {'status':'pending','missing':missing+([] if completion else ['crossover recovery confirmation']),'selected_profile':None}
 required=criteria['required'];gates=[]
 def gate(name,passed,actual=None,limit=None):gates.append({'name':name,'passed':bool(passed),'actual':actual,'limit':limit})
 other={**baseline,**criteria['alternate_diff']}
 gate('profiles match the planned single-flag comparison',before['profile']==baseline and after['profile']==baseline and all(s['profile']==other for s in alternate))
 gate('criteria frozen before alternate capture',all(s['started_epoch']>=criteria['frozen_epoch'] for s in alternate))
 gate('crossover recovered without a reboot or abort',not completion.get('aborted') and completion.get('baseline_restored') and completion.get('start_boot')==completion.get('boot_id') and all(not s['counts'].get('resets',0) for s in ordered))
 gate('fresh frame rate',min(s['fresh_fps'] for s in ordered)>=required['minimum_fresh_fps_each'],min(s['fresh_fps'] for s in ordered),required['minimum_fresh_fps_each'])
 ages=[s.get('age_p95_ms') for s in ordered];gate('relay age P95',all(isinstance(v,(int,float)) and v<=required['maximum_relay_age_p95_ms_each'] for v in ages),ages,required['maximum_relay_age_p95_ms_each'])
 gate('alternate outside-bed point fraction',max(s['outside_point_fraction'] for s in alternate)<=required['maximum_alternate_outside_point_fraction'],max(s['outside_point_fraction'] for s in alternate),required['maximum_alternate_outside_point_fraction'])
 for key in ['send_failures','queue_drops']:
  values=[]
  for s in ordered:
   a=s.get('health_before',{}).get('cloud',{}).get(key);b=s.get('health_after',{}).get('cloud',{}).get(key);values.append(b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) and b>=a else None)
  gate('cloud '+key,all(v==required['cloud_'+key+'_delta_each'] for v in values),values,required['cloud_'+key+'_delta_each'])
 aggregate={}
 for label,method in methods.items():
  rows={r['segment']:r for r in method.get('segments',[])}
  if any(s['segment'] not in rows for s in ordered):return {'status':'pending','missing':['exact runtime replay: '+label],'selected_profile':None}
  def mean(ss,key):
   rr=[rows[s['segment']] for s in ss];return sum(r[key]*r['samples'] for r in rr)/max(1,sum(r['samples'] for r in rr))
  baseline_rows=[before,after];stats={}
  for short,key in [('two','bed_two_recent_fraction'),('many','bed_more_than_two_recent_fraction'),('zero','bed_zero_recent_fraction')]:
   a=mean(baseline_rows,key);b=mean(alternate,key);stats[short]={'baseline':a,'alternate':b,'difference':b-a}
  gate(label+' two-group gain',stats['two']['difference']>=required['minimum_two_recent_fraction_gain_each_frozen_method'],stats['two']['difference'],required['minimum_two_recent_fraction_gain_each_frozen_method'])
  gate(label+' fragmentation increase',stats['many']['difference']<=required['maximum_many_recent_fraction_increase_each_method'],stats['many']['difference'],required['maximum_many_recent_fraction_increase_each_method'])
  gate(label+' zero-group increase',stats['zero']['difference']<=required['maximum_zero_recent_fraction_increase_each_method'],stats['zero']['difference'],required['maximum_zero_recent_fraction_increase_each_method'])
  aggregate[label]=stats
 passed=all(g['passed'] for g in gates)
 return {'status':'evaluated','alternate_passed':passed,'selected_profile':other if passed else baseline,'gates':gates,'aggregate':aggregate,'segments':[s['segment'] for s in ordered],'limitation':criteria['limitation'],'interpretation':'Practical return/grouping proxy comparison only; no verified human-count accuracy or automatic hardware mutation.'}
def main():
 criteria_path=OUT/'hardware-crossover-criteria.json'
 if not criteria_path.exists():return
 read=lambda name,default:json.loads((OUT/name).read_text()) if (OUT/name).exists() else default
 result=evaluate(read(criteria_path.name,{}),read('baseline.json',{})['active'],[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))],{'earlier':read('runtime-replay.json',{}),'density':read('density-runtime-replay.json',{})},read('crossover-complete.json',{}))
 target=OUT/'crossover-evaluation.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2));temp.replace(target);print('crossover evaluation:',result['status'],flush=True)
if __name__=='__main__':main()
