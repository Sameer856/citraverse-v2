#!/usr/bin/env python3
"""Audit post-selection holdout data without redefining the frozen candidate."""
import json,pathlib,datetime as dt
ROOT=pathlib.Path(__file__).resolve().parents[2];OUT=ROOT/'output/radar_overnight_20261125'
def evaluate(choice,segments,parents,display,regressions,completion):
 label=choice['selected_method'];parent=parents.get(label,{})
 limits=choice.get('holdout_criteria',{});reference=choice.get('selection_reference')
 if not limits or not reference:return {'status':'unverified','reason':'Frozen holdout criteria or selection reference missing'}
 if not choice.get('parent_engine_hash') or parent.get('engine_hash')!=choice['parent_engine_hash']:return {'status':'unverified','reason':'Frozen parent engine hash mismatch'}
 bounded=choice['display_policy']=='bounded'
 if bounded and (not choice.get('display_engine_hash') or display.get('engine_hash')!=choice['display_engine_hash']):return {'status':'unverified','reason':'Frozen display engine hash mismatch'}
 rows={r['segment']:r for r in (display if bounded else parent).get('segments',[])}
 after=[s for s in segments if s['started_epoch']>=choice['frozen_epoch'] and s['started_epoch']<choice['planned_capture_end_epoch']]
 selected=[s for s in after if s['profile']==choice['selected_profile']];other=[s['segment'] for s in after if s['profile']!=choice['selected_profile']]
 current_regressions=[r for r in regressions if r.get('epoch',choice['frozen_epoch'])>=choice['frozen_epoch']]
 if any(s['segment'] not in rows for s in selected):return {'status':'pending','reason':'Exact holdout replay not finished','regressions':current_regressions}
 total_minutes=sum(s['duration_s'] for s in selected)/60;summary=[];samples=0;totals={'two':0,'zero':0,'many':0}
 for s in selected:
  row=rows[s['segment']];n=row['samples']
  if not isinstance(s.get('age_p95_ms'),(int,float)) or not isinstance(s.get('fresh_fps'),(int,float)) or not isinstance(s.get('longest_outage_s'),(int,float)) or s.get('duration_s',0)<=0 or s.get('counts',{}).get('fresh',0)<=0:return {'status':'unverified','reason':'Incomplete holdout telemetry: '+s['segment']}
  if n<=0:return {'status':'unverified','reason':'Holdout has no sampled fresh evidence: '+s['segment']}
  if bounded:
   values=row['methods'][label];fractions={k:values['tolerant_'+k+'_recent_fraction'] for k in totals}
  else:fractions={k:row['bed_'+('more_than_two' if k=='many' else k)+'_recent_fraction'] for k in totals}
  for k in totals:totals[k]+=fractions[k]*n
  samples+=n;summary.append({'segment':s['segment'],'minutes':s['duration_s']/60,'fresh_fps':s['fresh_fps'],'relay_age_p95_ms':s.get('age_p95_ms'),'longest_receive_gap_s':s['longest_outage_s'],**{k+'_recent_fraction':v for k,v in fractions.items()}})
 def delta_sum(key):
  values=[]
  for s in selected:
   a=s.get('health_before',{}).get('cloud',{}).get(key);b=s.get('health_after',{}).get('cloud',{}).get(key)
   values.append(b-a if isinstance(a,(int,float)) and isinstance(b,(int,float)) and b>=a else None)
  return {'known_delta':sum(v for v in values if v is not None),'unknown_windows':sum(v is None for v in values)}
 duration=sum(s['duration_s'] for s in selected);minimum_minutes=limits['minimum_minutes']
 metrics={k+'_recent_fraction':totals[k]/max(1,samples) for k in totals};metrics.update({'fresh_fps':sum(s['counts'].get('fresh',0) for s in selected)/max(1,duration),'fresh_frames':sum(s['counts'].get('fresh',0) for s in selected),'sampled_seconds':samples,'longest_receive_gap_s':max((s['longest_outage_s'] for s in selected),default=0),'maximum_segment_relay_p95_ms':max((s.get('age_p95_ms') or 0 for s in selected),default=0),'missing_frame_indices':sum(s['counts'].get('missing_frames',0) for s in selected),'cloud':{key:delta_sum(key) for key in ['reconnects','dropped','queue_drops','send_failures']}})
 quality=[s['segment'] for s in selected if s['fresh_fps']<limits['minimum_fresh_fps'] or s['age_p95_ms']>limits['maximum_segment_relay_p95_ms']]
 behavior={'two_recent_nonregression':metrics['two_recent_fraction']>=reference['two']-limits['maximum_two_recent_fraction_decline_from_selection']-1e-12,'fragmentation_limit':metrics['many_recent_fraction']<=reference['many']+limits['maximum_many_recent_fraction_increase_from_selection']+1e-12,'zero_group_limit':metrics['zero_recent_fraction']<=reference['zero']+limits['maximum_zero_recent_fraction_increase_from_selection']+1e-12}
 capture_complete=False
 if completion.get('selected_observation') and completion.get('time'):
  capture_complete=dt.datetime.fromisoformat(completion['time']).timestamp()>=choice['planned_capture_end_epoch']
 live_verified=bool(completion.get('active_verified') and completion.get('active_profile')==choice['selected_profile'])
 minimum_met=total_minutes+1e-8>=minimum_minutes
 qualified=capture_complete and minimum_met and live_verified and not current_regressions and not quality and all(behavior.values()) and completion.get('startup_profile_unchanged') is True and not any(v['unknown_windows'] for v in metrics['cloud'].values())
 status=('complete' if qualified else 'complete_with_limits') if capture_complete else ('running' if selected else 'awaiting_windows')
 return {'status':status,'completed_windows':len(selected),'minutes':total_minutes,'minimum_required_minutes':minimum_minutes,'minimum_met':minimum_met,'capture_completed_at_planned_end':capture_complete,'selected_configuration_live_verified':live_verified,'selected_configuration_passed_holdout_gates':bool(qualified),'metrics':metrics,'windows':summary,'other_profile_windows_after_freeze':other,'regressions':current_regressions,'quality_problem_windows':quality,'behavior_gates':behavior,'selection_reference':reference,'startup_profile_unchanged':completion.get('startup_profile_unchanged'),'interpretation':'Fresh-group and transport evidence only. Reported two occupants were not independently annotated; no human-count accuracy is inferred.'}
def main():
 read=lambda n,d:json.loads((OUT/n).read_text()) if (OUT/n).exists() else d
 if not (OUT/'final-method-selection.json').exists():return
 result=evaluate(read('final-method-selection.json',{}),[json.loads(p.read_text()) for p in sorted(OUT.glob('segment-*.json'))],{'earlier':read('runtime-replay.json',{}),'density':read('density-runtime-replay.json',{})},read('display-runtime-replay.json',{}),read('final-regressions.json',{}).get('events',[]),read('complete.json',{}))
 target=OUT/'final-holdout-analysis.json';temp=target.with_suffix('.tmp');temp.write_text(json.dumps(result,indent=2));temp.replace(target);print('final holdout:',result['status'],flush=True)
if __name__=='__main__':main()
