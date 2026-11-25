#!/usr/bin/env python3
"""Validate one frozen final candidate; fall back permanently on a regression."""
import asyncio,json,time,pathlib,hashlib
import httpx
import run as r
async def main():
 baseline_record=json.loads((r.OUT/'baseline.json').read_text());r.BASE=baseline_record['active'];choice=json.loads((r.OUT/'final-method-selection.json').read_text());selected=choice['selected_profile']
 if selected not in [r.BASE,{**r.BASE,'static_rm':0}]:raise ValueError('Final profile must be one of the two tested static-return settings')
 regressions=json.loads((r.OUT/'final-regressions.json').read_text()).get('events',[]) if (r.OUT/'final-regressions.json').exists() else []
 fallback=bool(regressions);target=dict(r.BASE if fallback else selected);needs_apply=True
 results=[json.loads(p.read_text()) for p in sorted(r.OUT.glob('segment-*.json'))];failures=json.loads((r.OUT/'comparison.json').read_text()).get('failures',[])
 def regression(error):
  nonlocal target,fallback,needs_apply
  entry={'selection_epoch':choice['frozen_epoch'],'time':r.stamp(),'epoch':time.time(),'error_class':type(error).__name__,'reason':str(error),'from_profile':dict(target),'fallback_profile':r.BASE}
  regressions.append(entry);failures.append({'label':'final-observation','error':type(error).__name__+': '+str(error)});r.dump('final-regressions.json',{'events':regressions});r.event('final_candidate_regression',**entry)
  target=dict(r.BASE);fallback=True;needs_apply=True
 async with httpx.AsyncClient(base_url=r.ORIGIN,timeout=20) as client:
  start={'time':r.stamp(),'selected_profile':selected,'selection_epoch':choice['frozen_epoch'],'collector_sha256':r.CODE_HASH,'observer_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
  history=r.OUT/'final-observation-start-history.jsonl';previous=r.OUT/'final-observation-start.json'
  if not history.exists() and previous.exists():history.write_text(json.dumps(json.loads(previous.read_text()))+'\n')
  with history.open('a') as file:file.write(json.dumps(start)+'\n')
  r.dump('final-observation-start.json',start)
  while time.time()<r.END-600:
   try:
    state=await r.rpc(client)
    if state.get('active') not in [r.BASE,selected]:raise r.ExternalChange('External profile is outside the final comparison; leaving it alone')
    if needs_apply:
     if not fallback and choice.get('expected_boot') is not None and state.get('boot_id')!=choice['expected_boot']:raise r.DeviceRestart('New boot before final validation; baseline fallback selected')
     await r.apply(client,target,'final-baseline-fallback' if fallback else 'final-selected-profile');needs_apply=False
    else:
     if state.get('boot_id')!=r.EXPECTED_BOOT:raise r.DeviceRestart('Reboot between final observation windows')
     if state.get('active')!=target:raise r.ExternalChange('External profile changed between final windows')
    label='final-baseline-fallback' if fallback else 'final-selected'
    result=await r.capture(client,target,label,min(1200,r.END-time.time()-600));results.append(result)
    r.dump('comparison.json',{'updated':r.stamp(),'results':results,'failures':failures})
    if result['fresh_fps']<.9*(1000/target['frame_ms']) or result.get('age_p95_ms',0)>350:raise r.RadarStall('Final-window fresh-rate or relay-age gate failed')
   except r.ExternalChange:
    r.event('stopped_external_change');raise
   except Exception as error:
    regression(error);r.dump('comparison.json',{'updated':r.stamp(),'results':results,'failures':failures});await asyncio.sleep(10)
  state=None;h=None
  try:state=await r.rpc(client);h=await r.health(client)
  except Exception as error:
   ended={'time':r.stamp(),'selection_epoch':choice['frozen_epoch'],'planned_capture_end_epoch':r.END-600,'selected_profile':selected,'target_profile':target,'incomplete':True,'active_verified':False,'startup_profile_unchanged':None,'fallback':fallback,'regressions':len(regressions),'error_class':type(error).__name__,'reason':str(error)}
   r.dump('final-device-state.json',{'time':r.stamp(),'tuning':state,'health':h,'verification_error':str(error)});r.dump('observation-ended.json',ended);r.event('final_observation_unverified',error_class=ended['error_class'],reason=ended['reason']);return
  verified=state.get('active')==target and state.get('frames_verified') and state.get('frames_recent') and not state.get('busy')
  r.dump('final-device-state.json',{'time':r.stamp(),'tuning':state,'health':h})
  r.dump('complete.json',{'time':r.stamp(),'results':len(results),'selected_observation':True,'selected_profile':selected,'active_profile':state.get('active'),'active_verified':bool(verified),'baseline_restored':state.get('active')==r.BASE,'startup_profile_unchanged':state.get('saved')==baseline_record.get('saved'),'fallback':fallback,'regressions':len(regressions),'boot_id':state.get('boot_id')})
  r.event('final_observation_complete',active_verified=bool(verified),fallback=fallback,regressions=len(regressions))
if __name__=='__main__':asyncio.run(main())
