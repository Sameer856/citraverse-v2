import copy,unittest
from evaluate_crossover import evaluate
class EvaluationTests(unittest.TestCase):
 def fixture(self):
  baseline={'static_rm':1,'frame_ms':50};criteria={'frozen_epoch':100,'comparison':{'baseline_before':'pre','alternate_labels':['B1','B2'],'baseline_after_label':'Apost'},'alternate_diff':{'static_rm':0},'required':{'minimum_fresh_fps_each':18,'maximum_relay_age_p95_ms_each':350,'maximum_alternate_outside_point_fraction':.25,'minimum_two_recent_fraction_gain_each_frozen_method':.10,'maximum_many_recent_fraction_increase_each_method':.05,'maximum_zero_recent_fraction_increase_each_method':.01,'cloud_send_failures_delta_each':0,'cloud_queue_drops_delta_each':0},'limitation':'Unverified grouping proxy'}
  segments=[];rows=[]
  for segment,label,alternate in [('pre','Apre',False),('b1','B1',True),('b2','B2',True),('post','Apost',False)]:
   segments.append({'segment':segment,'label':label,'profile':{**baseline,'static_rm':0 if alternate else 1},'started_epoch':200,'counts':{},'fresh_fps':20,'age_p95_ms':200,'outside_point_fraction':.1,'health_before':{'cloud':{'send_failures':0,'queue_drops':0}},'health_after':{'cloud':{'send_failures':0,'queue_drops':0}}})
   rows.append({'segment':segment,'samples':100,'bed_two_recent_fraction':.9 if alternate else .7,'bed_more_than_two_recent_fraction':.04,'bed_zero_recent_fraction':.01})
  methods={'earlier':{'segments':copy.deepcopy(rows)},'density':{'segments':copy.deepcopy(rows)}};completion={'aborted':False,'baseline_restored':True,'start_boot':7,'boot_id':7}
  return criteria,baseline,segments,methods,completion
 def test_incomplete_is_pending_without_a_selected_profile(self):
  args=list(self.fixture());args[2]=args[2][:-1];r=evaluate(*args);self.assertEqual(r['status'],'pending');self.assertIsNone(r['selected_profile'])
 def test_clear_proxy_improvement_selects_only_the_alternate_flag(self):
  args=self.fixture();r=evaluate(*args);self.assertTrue(r['alternate_passed']);self.assertEqual(r['selected_profile'],{'static_rm':0,'frame_ms':50})
 def test_fragmentation_or_unknown_cloud_counters_cannot_pass(self):
  args=list(self.fixture());args[3]['density']['segments'][1]['bed_more_than_two_recent_fraction']=.5;r=evaluate(*args);self.assertFalse(r['alternate_passed']);self.assertEqual(r['selected_profile'],args[1])
  args=list(self.fixture());args[2][1]['health_after']['cloud'].pop('queue_drops');self.assertFalse(evaluate(*args)['alternate_passed'])
 def test_reboot_and_late_criteria_reject_an_apparent_gain(self):
  args=list(self.fixture());args[4]['boot_id']=8;self.assertFalse(evaluate(*args)['alternate_passed'])
  args=list(self.fixture());args[0]['frozen_epoch']=300;self.assertFalse(evaluate(*args)['alternate_passed'])
 def test_missing_exact_replay_stays_pending(self):
  args=list(self.fixture());args[3]['density']['segments'].pop();self.assertEqual(evaluate(*args)['status'],'pending')
 def test_abort_without_post_window_is_terminal_baseline_fallback(self):
  args=list(self.fixture());args[2]=args[2][:-1];args[4]['aborted']=True;args[4]['boot_id']=8
  result=evaluate(*args);self.assertEqual(result['status'],'evaluated');self.assertFalse(result['alternate_passed']);self.assertEqual(result['selected_profile'],args[1]);self.assertIn('baseline after',result['missing'])
if __name__=='__main__':unittest.main()
