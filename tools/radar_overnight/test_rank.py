import unittest
from rank import metric_candidates,score
class RankingTests(unittest.TestCase):
 def test_temporal_suffix_and_missing_data(self):
  m=metric_candidates({'cluster_fractions':{}},{'fractions':{'w0.5-r0.3-min6-two_recent':.8,'w0.5-r0.3-min6-many_recent':.1}})
  t=[x for x in m if x['method']=='w0.5-r0.3-min6'][0];self.assertEqual(t['two'],.8);self.assertEqual(t['many'],.1);self.assertEqual(t['window'],.5)
 def test_fragmentation_and_old_evidence_not_rewarded(self):
  clean={'two':.8,'many':0,'zero':0,'window':.2};bad={**clean,'many':.2};self.assertGreater(score(clean,1,1,20),score(bad,1,1,20))
if __name__=='__main__':unittest.main()
