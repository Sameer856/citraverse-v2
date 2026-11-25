import collections,unittest
from temporal_analyze import unique_points,measure
class TemporalTests(unittest.TestCase):
 def test_repeated_point_is_not_extra_support(self):
  p=(.4,1,.8,0,25,True);self.assertEqual(len(unique_points([(0,[p]),(.1,[p])],.1,.5)),1)
 def test_old_evidence_not_called_recent(self):
  ps=[(.4+i*.06,1,.8,0,25,True) for i in range(6)];self.assertEqual(measure([(0,ps)],.5,1,.2,3),(1,0))
 def test_two_actual_recent_groups_remain_two(self):
  ps=[(.4+i*.05,1,.8,0,25,True) for i in range(4)]+[(1.1+i*.05,1,.8,0,25,True) for i in range(4)];self.assertEqual(measure([(.1,ps)],.1,.5,.2,3),(2,2))
 def test_expired_points_disappear(self):
  ps=[(.4+i*.06,1,.8,0,25,True) for i in range(6)];self.assertEqual(measure([(0,ps)],1.1,1,.2,3),(0,0))
if __name__=='__main__':unittest.main()
