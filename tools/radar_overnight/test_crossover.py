import json,pathlib,tempfile,unittest
from unittest.mock import patch,AsyncMock
import crossover as c
class FakeClient:
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
class CrossoverTests(unittest.IsolatedAsyncioTestCase):
 async def simulate(self,fault=None,rate=20):
  baseline={'frequency':58000,'range_mm':6400,'resolution_mm':25,'speed_mm_s':3200,'speed_step_mm_s':200,'frame_ms':50,'static_rm':1,'cfar_value':80,'cfar_method':-1,'clutter_rm':0}
  state={'active':baseline,'boot_id':7};calls=[]
  async def apply(client,profile,label):calls.append((label,dict(profile)));state['active']=dict(profile);return state
  async def capture(client,profile,label,seconds):
   if fault:raise fault('Injected failure')
   return {'label':label,'profile':profile,'fresh_fps':rate,'counts':{'frames':24000}}
  with tempfile.TemporaryDirectory() as d:
   out=pathlib.Path(d);(out/'baseline.json').write_text(json.dumps({'active':baseline}));(out/'comparison.json').write_text('{"failures":[]}')
   observer=AsyncMock();cap=AsyncMock(side_effect=capture)
   with patch.object(c.r,'OUT',out),patch.object(c.r,'apply',side_effect=apply),patch.object(c.r,'capture',cap),patch.object(c.r,'rpc',AsyncMock(side_effect=lambda client:dict(state))),patch.object(c.r,'main',observer),patch.object(c.r,'event'),patch.object(c.httpx,'AsyncClient',return_value=FakeClient()),patch.dict(c.os.environ,{},clear=False):
    if fault is c.r.ExternalChange:
     with self.assertRaises(c.r.ExternalChange):await c.main()
    else:await c.main()
   result=json.loads((out/'crossover-complete.json').read_text()) if (out/'crossover-complete.json').exists() else None
   return baseline,state,calls,cap.await_count,observer.await_count,result
 async def test_success_changes_only_static_flag_then_restores(self):
  baseline,state,calls,captures,observations,result=await self.simulate()
  self.assertEqual(captures,3);self.assertEqual(observations,1);self.assertEqual(state['active'],baseline);self.assertFalse(result['aborted'])
  for label,profile in calls:self.assertLessEqual({k for k in profile if profile[k]!=baseline[k]},{'static_rm'})
 async def test_stall_aborts_remaining_alternate_windows_and_restores(self):
  baseline,state,calls,captures,observations,result=await self.simulate(c.r.RadarStall)
  self.assertEqual(captures,1);self.assertEqual(observations,1);self.assertEqual(state['active'],baseline);self.assertTrue(result['aborted']);self.assertEqual(len(calls),2)
 async def test_low_fresh_rate_aborts_and_restores(self):
  baseline,state,calls,captures,observations,result=await self.simulate(rate=5)
  self.assertEqual(captures,1);self.assertEqual(state['active'],baseline);self.assertTrue(result['aborted'])
 async def test_external_operator_change_is_never_overridden(self):
  baseline,state,calls,captures,observations,result=await self.simulate(c.r.ExternalChange)
  self.assertEqual(len(calls),1);self.assertEqual(observations,0);self.assertIsNone(result)
if __name__=='__main__':unittest.main()
