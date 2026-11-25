import importlib.util,pathlib,struct,unittest
spec=importlib.util.spec_from_file_location('runner',pathlib.Path(__file__).with_name('run.py'));r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class ProtocolTests(unittest.TestCase):
 def packet(self):
  tlv=struct.pack('<BBHhhhhHH',4,3,12,-125,245,70,-50,1500,0)
  return struct.pack('<6I',0x32524452,1234,44,99,len(tlv)//4,0)+tlv
 def test_decode_units_and_concatenation(self):
  frames=list(r.decode(self.packet()*2));self.assertEqual(len(frames),2);self.assertEqual(frames[0][3][0],(-1.25,2.45,.7,-.5,15,True))
 def test_reject_truncation(self):
  for b in [self.packet()[:-1],b'bad',struct.pack('<6I',0,0,0,0,0,0)]:
   with self.assertRaises(ValueError):list(r.decode(b))
 def test_mount_matches_dashboard_basis(self):
  x,y,z,*_=r.world((0,1,0,0,1,False));self.assertAlmostEqual(x,-.6536357597);self.assertAlmostEqual(y,2.1536357597);self.assertAlmostEqual(z,1.8263518223)
 def test_empty_roi_and_outside_returns(self):
  f=r.features([]);self.assertEqual(f['bed'],0);self.assertIsNone(f['bed_top']);self.assertEqual(r.features([(100,100,100,0,0,False)])['room'],0)
class AuditTests(unittest.TestCase):
 def test_missing_health_is_not_a_reboot(self):
  r.audit_capture({'frames':100},{},{'boot_id':7,'active':{}},{},7,{})
 def test_actual_reset_is_rejected(self):
  for health,state,counts in [({'frames':5},{'boot_id':7,'active':{}},{}),({}, {'boot_id':8,'active':{}},{}),({}, {'boot_id':7,'active':{}},{'resets':1})]:
   with self.assertRaises(r.DeviceRestart):r.audit_capture({'frames':100},health,state,{},7,counts)
 def test_external_profile_change_is_rejected(self):
  with self.assertRaises(r.ExternalChange):r.audit_capture({}, {}, {'boot_id':7,'active':{'changed':1}}, {},7,{})
if __name__=='__main__':unittest.main()

