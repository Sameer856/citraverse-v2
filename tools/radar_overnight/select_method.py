#!/usr/bin/env python3
"""Read-only choice between frozen methods; never configures the PCB."""
import json,pathlib,time
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def close_insufficient_selection(result,criteria,hardware,now):
 if result.get('status')=='pending' and result.get('reason')=='Insufficient completed post-freeze data on selected hardware' and now>=criteria['selection_cutoff_epoch']:
  return {**result,'status':'inconclusive','selected_profile':hardware.get('selected_profile'),'reason':'Selection cutoff closed without enough eligible completed data. No optimized method is selected; any conservative retention is recorded separately in the final-method selection.'}
 return result
def select(criteria,hardware,segments,parents,display,density_freeze,display_freeze,minimum_fps=18):
 if hardware.get('status')!='evaluated':return {'status':'pending','reason':'Hardware crossover is incomplete'}
 profile=hardware['selected_profile'];cutoff=criteria['selection_cutoff_epoch']
 eligible=[s for s in segments if s['profile']==profile and s['started_epoch']>=density_freeze and s['ended_epoch']<=cutoff and s['fresh_fps']>=minimum_fps]
 minutes=sum(s['duration_s'] for s in eligible)/60
 if minutes+1e-8<criteria['minimum_completed_minutes']:return {'status':'pending','reason':'Insufficient completed post-freeze data on selected hardware','minutes':minutes}
 aggregate={};maps={label:{r['segment']:r for r in value.get('segments',[])} for label,value in parents.items()}
 def weighted(rows,key):return sum(r[key]*r['samples'] for r in rows)/max(1,sum(r['samples'] for r in rows))
 for label,rows in maps.items():
  if any(s['segment'] not in rows or rows[s['segment']]['samples']<=0 for s in eligible):return {'status':'pending','reason':'Exact runtime replay missing: '+label}
  rr=[rows[s['segment']] for s in eligible];aggregate[label]={short:weighted(rr,key) for short,key in [('two','bed_two_recent_fraction'),('many','bed_more_than_two_recent_fraction'),('zero','bed_zero_recent_fraction')]}
 delta={key:aggregate['density'][key]-aggregate['earlier'][key] for key in ['two','many','zero']};limits=criteria['density_becomes_default_only_if']
 checks={'two_recent_gain':delta['two']+1e-12>=limits['two_recent_fraction_gain_at_least'],'fragmentation_not_worse':delta['many']<=limits['many_recent_fraction_increase_at_most']+1e-12,'zero_group_time_not_worse':delta['zero']<=limits['zero_recent_fraction_increase_at_most']+1e-12}
 chosen='density' if all(checks.values()) else 'earlier'
 policy_segments=[s for s in eligible if s['started_epoch']>=display_freeze];policy_minutes=sum(s['duration_s'] for s in policy_segments)/60;lookup={r['segment']:r for r in display.get('segments',[])}
 if policy_minutes+1e-8<criteria['minimum_completed_minutes'] or any(s['segment'] not in lookup for s in policy_segments):return {'status':'pending','reason':'Display policy prospective replay incomplete','parent_candidate':chosen}
 rows=[{**lookup[s['segment']]['methods'][chosen],'samples':lookup[s['segment']]['samples']} for s in policy_segments];policy_delta={key:weighted(rows,'tolerant_'+key+'_recent_fraction')-weighted(rows,'strict_'+key+'_recent_fraction') for key in ['two','many','zero']}
 cap=criteria['display_policy_acceptance'];policy_checks={'two_group_noninferiority':policy_delta['two']>=-cap['prospective_two_recent_fraction_decrease_at_most']-1e-12,'fragmentation_limit':policy_delta['many']<=cap['prospective_many_recent_fraction_increase_at_most']+1e-12,'zero_group_limit':policy_delta['zero']<=cap['prospective_zero_recent_fraction_increase_at_most']+1e-12}
 return {'status':'evaluated','selected_profile':profile,'selected_method':chosen,'selected_options':parents[chosen]['options'],'density_gates':checks,'aggregate':aggregate,'density_minus_earlier':delta,'selection_segments':[s['segment'] for s in eligible],'selection_minutes':minutes,'selection_cutoff_epoch':cutoff,'display_selection_segments':[s['segment'] for s in policy_segments],'display_policy_proposed':'bounded' if all(policy_checks.values()) else 'strict','display_replay_gates':policy_checks,'display_tolerant_minus_strict':policy_delta,'deployment_requires_strict_fall_checks':True,'limitation':'Engineering proxy selection only; no verified human count. Final selection must be frozen before a separate overnight holdout.'}
def main():
 read=lambda name,default:json.loads((OUT/name).read_text()) if (OUT/name).exists() else default
 if not (OUT/'software-selection-criteria.json').exists():return
 parents={label:{**read(name,{}),'options':read(freeze,{})['options']} for label,name,freeze in [('earlier','runtime-replay.json','frozen-bed-method-v2.json'),('density','density-runtime-replay.json','frozen-bed-density.json')]}
 result=select(read('software-selection-criteria.json',{}),read('crossover-evaluation.json',{}),[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))],parents,read('display-runtime-replay.json',{}),read('frozen-bed-density.json',{})['frozen_epoch'],read('frozen-display-policy.json',{})['frozen_epoch'],read('hardware-crossover-criteria.json',{})['required']['minimum_fresh_fps_each']);result['computed_epoch']=time.time()
 result=close_insufficient_selection(result,read('software-selection-criteria.json',{}),read('crossover-evaluation.json',{}),time.time())
 target=OUT/'software-selection-evaluation.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2));temp.replace(target);print('software selection:',result['status'],flush=True)
if __name__=='__main__':main()
