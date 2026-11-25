import collections,unittest
from temporal_analyze import unique_points,measure,anisotropic_groups
class TemporalTests(unittest.TestCase):
 def test_repeated_point_is_not_extra_support(self):
  p=(.4,1,.8,0,25,True);self.assertEqual(len(unique_points([(0,[p]),(.1,[p])],.1,.5)),1)
 def test_old_evidence_not_called_recent(self):
  ps=[(.4+i*.06,1,.8,0,25,True) for i in range(6)];self.assertEqual(measure([(0,ps)],.5,1,.2,3),(1,0))
 def test_two_actual_recent_groups_remain_two(self):
  ps=[(.4+i*.05,1,.8,0,25,True) for i in range(4)]+[(1.1+i*.05,1,.8,0,25,True) for i in range(4)];self.assertEqual(measure([(.1,ps)],.1,.5,.2,3),(2,2))
 def test_bed_aligned_groups_join_head_feet_but_keep_side_by_side_columns(self):
  ps=[(.4,1,.8,0,25,True,0),(.4,2,.8,0,25,True,0),(1.1,1,.8,0,25,True,0),(1.1,2,.8,0,25,True,0)]
  self.assertEqual(len(anisotropic_groups(ps,.2,1.4)),2)
 def test_anisotropic_groups_do_not_force_two(self):
  ps=[(.4,1,.8,0,25,True,0),(.4,2,.8,0,25,True,0)]
  self.assertEqual(len(anisotropic_groups(ps,.2,1.4)),1)
 def test_accelerated_groups_match_reference_on_random_clouds(self):
  import random,temporal_analyze as t
  rng=random.Random(4);engine=t.np
  for _ in range(20):
   ps=[(rng.random(),rng.random()*2,0,0,0,False,0) for i in range(30)]
   fast=sorted(map(len,t.anisotropic_groups(ps,.2,1)));t.np=None
   slow=sorted(map(len,t.anisotropic_groups(ps,.2,1)));t.np=engine
   self.assertEqual(fast,slow)
 def test_expired_points_disappear(self):
  ps=[(.4+i*.06,1,.8,0,25,True) for i in range(6)];self.assertEqual(measure([(0,ps)],1.1,1,.2,3),(0,0))
if __name__=='__main__':unittest.main()
