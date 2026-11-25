import copy,datetime as dt,unittest
from evaluate_final import evaluate
class HoldoutTests(unittest.TestCase):
 def fixture(self):
  limits={'minimum_minutes':20,'minimum_fresh_fps':18,'maximum_segment_relay_p95_ms':350,'maximum_two_recent_fraction_decline_from_selection':.10,'maximum_many_recent_fraction_increase_from_selection':.05,'maximum_zero_recent_fraction_increase_from_selection':.05}
  choice={'selected_method':'earlier','selected_profile':{'static_rm':1},'display_policy':'bounded','frozen_epoch':100,'planned_capture_end_epoch':10000,'parent_engine_hash':'parent','display_engine_hash':'display','holdout_criteria':limits,'selection_reference':{'two':.8,'many':.05,'zero':.01}}
  cloud={'send_failures':0,'queue_drops':0,'reconnects':0,'dropped':0};s={'segment':'holdout','profile':{'static_rm':1},'started_epoch':200,'ended_epoch':1400,'duration_s':1200,'fresh_fps':20,'age_p95_ms':200,'longest_outage_s':.1,'counts':{'fresh':24000},'health_before':{'cloud':dict(cloud)},'health_after':{'cloud':dict(cloud)}}
  parents={'earlier':{'engine_hash':'parent','segments':[{'segment':'holdout','samples':100,'bed_two_recent_fraction':.8,'bed_more_than_two_recent_fraction':.05,'bed_zero_recent_fraction':.01}]}}
  display={'engine_hash':'display','segments':[{'segment':'holdout','samples':100,'methods':{'earlier':{'tolerant_two_recent_fraction':.8,'tolerant_many_recent_fraction':.05,'tolerant_zero_recent_fraction':.01}}}]}
  completion={'selected_observation':True,'time':dt.datetime.fromtimestamp(10000,dt.timezone.utc).isoformat(),'active_verified':True,'active_profile':{'static_rm':1},'startup_profile_unchanged':True}
  return [choice,[s],parents,display,[],completion]
 def test_complete_verified_holdout_can_pass_only_at_planned_end(self):
  a=self.fixture();self.assertTrue(evaluate(*a)['selected_configuration_passed_holdout_gates']);a[-1]['time']=dt.datetime.fromtimestamp(9000,dt.timezone.utc).isoformat();self.assertFalse(evaluate(*a)['selected_configuration_passed_holdout_gates']);self.assertEqual(evaluate(*a)['status'],'running')
 def test_preselection_and_other_profile_data_do_not_inflate_holdout(self):
  a=self.fixture();pre=copy.deepcopy(a[1][0]);pre.update(segment='pre',started_epoch=50);other=copy.deepcopy(a[1][0]);other.update(segment='other',profile={'static_rm':0});a[1]+=[pre,other];r=evaluate(*a);self.assertEqual(r['completed_windows'],1);self.assertEqual(r['other_profile_windows_after_freeze'],['other'])
 def test_engine_mismatch_and_missing_replay_are_unverified(self):
  a=self.fixture();a[3]['engine_hash']='changed';self.assertEqual(evaluate(*a)['status'],'unverified');a=self.fixture();a[3]['segments']=[];self.assertEqual(evaluate(*a)['status'],'pending')
 def test_regression_or_bad_grouping_cannot_be_reported_as_a_pass(self):
  a=self.fixture();a[4]=[{'epoch':500,'reason':'Reboot'}];self.assertFalse(evaluate(*a)['selected_configuration_passed_holdout_gates']);a=self.fixture();a[3]['segments'][0]['methods']['earlier']['tolerant_two_recent_fraction']=.2;self.assertFalse(evaluate(*a)['behavior_gates']['two_recent_nonregression']);self.assertEqual(evaluate(*a)['status'],'complete_with_limits')
 def test_unknown_telemetry_is_not_zero_loss(self):
  a=self.fixture();a[1][0]['health_after']['cloud'].pop('queue_drops');r=evaluate(*a);self.assertFalse(r['selected_configuration_passed_holdout_gates']);self.assertEqual(r['metrics']['cloud']['queue_drops']['unknown_windows'],1);a=self.fixture();a[1][0]['age_p95_ms']=None;self.assertEqual(evaluate(*a)['status'],'unverified')
 def test_final_active_profile_and_startup_state_must_match_evidence(self):
  a=self.fixture();a[-1]['active_profile']={'static_rm':0};self.assertFalse(evaluate(*a)['selected_configuration_passed_holdout_gates']);a=self.fixture();a[-1].pop('startup_profile_unchanged');self.assertFalse(evaluate(*a)['selected_configuration_passed_holdout_gates'])
if __name__=='__main__':unittest.main()
