import unittest,copy
from select_method import select,close_insufficient_selection
class SelectionTests(unittest.TestCase):
 def fixture(self):
  c={'selection_cutoff_epoch':2000,'minimum_completed_minutes':20,'density_becomes_default_only_if':{'two_recent_fraction_gain_at_least':.02,'many_recent_fraction_increase_at_most':0,'zero_recent_fraction_increase_at_most':.005},'display_policy_acceptance':{'prospective_two_recent_fraction_decrease_at_most':.01,'prospective_many_recent_fraction_increase_at_most':.01,'prospective_zero_recent_fraction_increase_at_most':.005}}
  h={'status':'evaluated','selected_profile':{'static_rm':1}};ss=[{'segment':'A','profile':{'static_rm':1},'started_epoch':200,'ended_epoch':1400,'fresh_fps':20,'duration_s':1200}]
  parents={label:{'options':{'minimum':3},'segments':[{'segment':'A','samples':100,'bed_two_recent_fraction':two,'bed_more_than_two_recent_fraction':many,'bed_zero_recent_fraction':.01}]} for label,two,many in [('earlier',.7,.1),('density',.8,.05)]}
  dm={label:{'strict_two_recent_fraction':p['segments'][0]['bed_two_recent_fraction'],'tolerant_two_recent_fraction':p['segments'][0]['bed_two_recent_fraction'],'strict_many_recent_fraction':.05,'tolerant_many_recent_fraction':.05,'strict_zero_recent_fraction':.01,'tolerant_zero_recent_fraction':.005} for label,p in parents.items()};d={'segments':[{'segment':'A','samples':100,'methods':dm}]}
  return [c,h,ss,parents,d,100,150]
 def test_pending_hardware_cannot_choose_a_method(self):
  a=self.fixture();a[1]['status']='pending';self.assertEqual(select(*a)['status'],'pending')
 def test_density_requires_a_practical_gain(self):
  a=self.fixture();self.assertEqual(select(*a)['selected_method'],'density');a[3]['density']['segments'][0]['bed_two_recent_fraction']=.71;self.assertEqual(select(*a)['selected_method'],'earlier')
 def test_bad_display_policy_does_not_become_default(self):
  a=self.fixture();a[4]['segments'][0]['methods']['density']['tolerant_many_recent_fraction']=.2;self.assertEqual(select(*a)['display_policy_proposed'],'strict')
 def test_later_holdout_does_not_change_the_selection(self):
  a=self.fixture();late=copy.deepcopy(a[2][0]);late.update(segment='future',started_epoch=2500,ended_epoch=3700);a[2].append(late);self.assertEqual(select(*a)['selection_segments'],['A'])
 def test_insufficient_duration_or_missing_replay_stays_pending(self):
  a=self.fixture();a[2][0]['duration_s']=600;self.assertEqual(select(*a)['status'],'pending');a=self.fixture();a[3]['density']['segments']=[];self.assertEqual(select(*a)['status'],'pending')
 def test_closed_cutoff_is_inconclusive_but_replay_delay_is_not(self):
  a=self.fixture();a[2][0]['duration_s']=600;r=select(*a)
  self.assertEqual(close_insufficient_selection(r,a[0],a[1],1999)['status'],'pending')
  self.assertEqual(close_insufficient_selection(r,a[0],a[1],2000)['status'],'inconclusive')
  a=self.fixture();a[3]['density']['segments']=[];r=select(*a);self.assertEqual(close_insufficient_selection(r,a[0],a[1],2001)['status'],'pending')
if __name__=='__main__':unittest.main()
