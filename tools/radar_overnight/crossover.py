#!/usr/bin/env python3
"""One bounded repeat of an already stable flag setting, then baseline observation."""
import asyncio,json,os,time
import httpx
import run as r
async def main():
 r.BASE=json.loads((r.OUT/'baseline.json').read_text())['active']
 results=[json.loads(p.read_text()) for p in sorted(r.OUT.glob('segment-*.json'))]
 prior=json.loads((r.OUT/'comparison.json').read_text());failures=prior.get('failures',[])
 alternate={**r.BASE,'static_rm':0};external=False;failed=False
 async with httpx.AsyncClient(base_url=r.ORIGIN,timeout=20) as client:
  state=await r.rpc(client)
  if state.get('active')!=r.BASE:raise r.ExternalChange('Expected baseline at crossover handoff; leaving external profile alone')
  expected=os.environ.get('RADAR_CROSSOVER_EXPECTED_BOOT')
  if expected and state.get('boot_id')!=int(expected):raise r.DeviceRestart('New boot since baseline observation; crossover not started')
  r.EXPECTED_BOOT=state['boot_id']
  r.dump('plan-crossover.json',{'time':r.stamp(),'reason':'Repeat only the already-tested literal-CFAR static-retention flag after stable baseline observation. No new frequency, range, speed, CFAR format, Wi-Fi, firmware or saved-profile changes. Prior aggressive sweeps remain suspended.','previous_baseline_window':'011-baseline-overnight-observation','sequence':[{'label':label,'profile':p,'seconds':1200} for label,p in [('crossover-static0-first',alternate),('crossover-static0-repeat',alternate),('crossover-baseline',r.BASE)]],'abort':'Any reboot, stale radar status, external change or failed fresh-rate gate stops further alternate captures; restore baseline unless an external operator changed it.'})
  try:
   for label,profile in [('crossover-static0-first',alternate),('crossover-static0-repeat',alternate),('crossover-baseline',r.BASE)]:
    await r.apply(client,profile,label)
    result=await r.capture(client,profile,label,1200);results.append(result)
    r.dump('comparison.json',{'updated':r.stamp(),'results':results,'failures':failures})
    if result['fresh_fps']<.8*(1000/profile['frame_ms']) or result['counts'].get('stale',0)>.05*max(1,result['counts']['frames']):raise r.RadarStall('Fresh-rate gate failed; no further alternate windows')
  except r.ExternalChange:
   external=True;r.event('stopped_external_change');raise
  except Exception as e:
   failed=True;failures.append({'label':'bounded-static-retention-crossover','error':type(e).__name__+': '+str(e)});r.event('crossover_aborted',error=str(e))
  finally:
   if not external:
    await r.apply(client,r.BASE,'crossover-restore-baseline')
    state=await r.rpc(client)
    r.dump('crossover-complete.json',{'time':r.stamp(),'aborted':failed,'baseline_restored':state.get('active')==r.BASE,'boot_id':state.get('boot_id')})
    r.dump('comparison.json',{'updated':r.stamp(),'results':results,'failures':failures})
 os.environ['RADAR_OBSERVE_ONLY']='1'
 await r.main()
if __name__=='__main__':asyncio.run(main())
