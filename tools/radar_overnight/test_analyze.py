import importlib.util,pathlib,struct,unittest
spec=importlib.util.spec_from_file_location('analysis',pathlib.Path(__file__).with_name('analyze.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class SpatialTests(unittest.TestCase):
 def test_two_separated_clouds(self):
  p=[(.4+i*.01,1,0,0,0) for i in range(6)]+[(1.1+i*.01,1,0,0,0) for i in range(6)]
  self.assertEqual(sorted(map(len,a.grouped(p,.2))),[6,6])
 def test_one_connected_cloud_is_not_forced_into_two(self):
  p=[(.4+i*.02,1,0,0,0) for i in range(20)]
  self.assertEqual(len(a.grouped(p,.2)),1)
 def test_horizontal_projection_does_not_split_one_body_by_height(self):
  p=[(.4,1,i*.01,0,0) for i in range(6)]+[(.4,1,1+i*.01,0,0) for i in range(6)]
  self.assertEqual(len(a.grouped(p,.2)),1);self.assertEqual(len(a.grouped(p,.2,3)),2)
 def test_density_clustering_rejects_sparse_bridge(self):
  p=[(.4+i*.01,1,0,0,0) for i in range(8)]+[(1.2+i*.01,1,0,0,0) for i in range(8)]+[(x,1,0,0,0) for x in [.6,.78,.96,1.1]]
  self.assertEqual(len(a.grouped(p,.2)),1);self.assertEqual(len(a.density_groups(p,.2,6)),2)
 def test_density_does_not_force_two_people(self):
  p=[(.4+i*.01,1,0,0,0) for i in range(15)];self.assertEqual(len(a.density_groups(p,.2,6)),1)
 def test_sparse_noise_remains_small(self):
  p=[(0,0,0,0,0),(1,1,0,0,0),(2,2,0,0,0)];self.assertEqual(list(map(len,a.grouped(p,.2))),[1,1,1])
 def test_3d_projection_math_matches_capture(self):
  tlv=struct.pack('<BBHhhhhHH',4,3,12,0,100,0,0,1500,0)
  data=struct.pack('<6I',0x32524452,1234,44,99,len(tlv)//4,0)+tlv
  age,p=next(a.frames(data));self.assertEqual(age,44);self.assertAlmostEqual(p[0][0],-.6536357597);self.assertAlmostEqual(p[0][2],1.8263518223)
if __name__=='__main__':unittest.main()
