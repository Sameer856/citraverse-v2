import json,pathlib,tempfile,unittest
from unittest.mock import patch,AsyncMock
import observe_selected as c
class FakeClient:
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
class Clock:
 value=0
 def now(self):return self.value
class ObservationTests(unittest.IsolatedAsyncioTestCase):
 async def simulate(self,fault=False,boot=7,prior_regression=False,external=False,end_unreachable=False):
  baseline={'static_rm':1,'frame_ms':50};selected={**baseline,'static_rm':0};clock=Clock();state={'active':{**baseline,'frequency':57000} if external else baseline,'saved':baseline,'boot_id':boot,'frames_verified':True,'frames_recent':True,'busy':False};calls=[];captures=[]
  async def apply(client,profile,label):calls.append(dict(profile));state['active']=dict(profile);c.r.EXPECTED_BOOT=state['boot_id'];return dict(state)
  async def capture(client,profile,label,seconds):
   captures.append(label)
   if fault and len(captures)==1:raise c.r.RadarStall('Injected stall')
   clock.value=2000;return {'segment':label,'label':label,'profile':dict(profile),'fresh_fps':20,'age_p95_ms':200,'counts':{'frames':20000}}
  async def rpc(client):
   if end_unreachable and clock.value>=2000:raise c.httpx.ConnectTimeout('Final status unavailable')
   return dict(state)
  with tempfile.TemporaryDirectory() as directory:
   out=pathlib.Path(directory);(out/'baseline.json').write_text(json.dumps({'active':baseline,'saved':baseline}));(out/'comparison.json').write_text('{"failures":[]}');(out/'final-method-selection.json').write_text(json.dumps({'selected_profile':selected,'frozen_epoch':0,'expected_boot':7}))
   if prior_regression:(out/'final-regressions.json').write_text('{"events":[{"reason":"Earlier stall"}]}')
   with patch.object(c.r,'OUT',out),patch.object(c.r,'END',1600),patch.object(c.time,'time',side_effect=clock.now),patch.object(c.r,'rpc',AsyncMock(side_effect=rpc)),patch.object(c.r,'health',AsyncMock(return_value={'cloud':{'connected':True}})),patch.object(c.r,'apply',side_effect=apply),patch.object(c.r,'capture',side_effect=capture),patch.object(c.r,'event'),patch.object(c.httpx,'AsyncClient',return_value=FakeClient()),patch.object(c.asyncio,'sleep',AsyncMock()):
    if external:
     with self.assertRaises(c.r.ExternalChange):await c.main()
    else:await c.main()
   result=json.loads((out/'complete.json').read_text()) if (out/'complete.json').exists() else None
   state['_unverified_end']=json.loads((out/'observation-ended.json').read_text()) if (out/'observation-ended.json').exists() else None
   return baseline,selected,state,calls,captures,result
 async def test_healthy_selected_profile_stays_active_without_startup_save(self):
  baseline,selected,state,calls,captures,result=await self.simulate();self.assertEqual(state['active'],selected);self.assertTrue(result['active_verified']);self.assertTrue(result['startup_profile_unchanged']);self.assertFalse(result['baseline_restored']);self.assertEqual(calls,[selected])
 async def test_stall_falls_back_and_does_not_retry_the_alternate(self):
  baseline,selected,state,calls,captures,result=await self.simulate(fault=True);self.assertEqual(calls,[selected,baseline]);self.assertEqual(state['active'],baseline);self.assertTrue(result['fallback']);self.assertEqual(captures,['final-selected','final-baseline-fallback'])
 async def test_new_boot_or_prior_regression_prevents_reapplying_alternate(self):
  for options in [{'boot':8},{'prior_regression':True}]:
   baseline,selected,state,calls,captures,result=await self.simulate(**options);self.assertEqual(calls,[baseline]);self.assertTrue(result['fallback']);self.assertEqual(state['saved'],baseline)
 async def test_external_profile_is_preserved(self):
  baseline,selected,state,calls,captures,result=await self.simulate(external=True);self.assertEqual(calls,[]);self.assertIsNone(result);self.assertEqual(state['active']['frequency'],57000)
 async def test_unreachable_final_state_ends_without_a_false_complete_marker(self):
  baseline,selected,state,calls,captures,result=await self.simulate(end_unreachable=True);self.assertIsNone(result);self.assertTrue(state['_unverified_end']['incomplete']);self.assertFalse(state['_unverified_end']['active_verified']);self.assertIsNone(state['_unverified_end']['startup_profile_unchanged']);self.assertEqual(calls,[selected])
if __name__=='__main__':unittest.main()
