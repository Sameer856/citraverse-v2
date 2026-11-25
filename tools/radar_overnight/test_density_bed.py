import unittest
try:
 from density_bed import density_groups
except ImportError:density_groups=None
@unittest.skipIf(density_groups is None,'NumPy runtime required')
class DensityTests(unittest.TestCase):
 def points(self,x):return [(x+i*.005,0,.8,0,20,True,0) for i in range(6)]
 def test_count_not_forced(self):
  self.assertEqual(density_groups([],1,1,4),[])
  self.assertEqual(len(density_groups(self.points(0),.2,1,4)),1)
  self.assertEqual(len(density_groups(self.points(0)+self.points(1),.2,1,4)),2)
 def test_sparse_bridge_cannot_connect_dense_bodies(self):
  points=self.points(0)+[(x,0,.8,0,20,True,0) for x in [.35,.7,1.05,1.4,1.75]]+self.points(2)
  self.assertEqual(len(density_groups(points,.4,1,4)),2)
 def test_sparse_noise_does_not_create_body(self):
  self.assertEqual(density_groups([(0,0,0),(2,0,0),(4,0,0)],.2,1,4),[])
if __name__=='__main__':unittest.main()
