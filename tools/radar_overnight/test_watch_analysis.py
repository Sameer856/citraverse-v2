import json,pathlib,tempfile,unittest
from unittest.mock import patch
import watch_analysis as w
class MonitorEndTests(unittest.TestCase):
 def simulate(self,marker=None,deadline=100,now=0):
  with tempfile.TemporaryDirectory() as directory:
   out=pathlib.Path(directory)
   if marker:(out/marker).write_text('{}')
   with patch.object(w.analyze,'OUT',out),patch.object(w.analyze,'main'),patch.object(w.time,'time',return_value=now),patch.object(w,'command') as commands,patch.dict(w.os.environ,{'RADAR_REPORT_CANVAS_PATH':''}):
    result=w.main(deadline)
   return result,json.loads((out/'analysis-monitor-ended.json').read_text()),(out/'complete.json').exists(),[call.args for call in commands.call_args_list]
 def test_unverified_end_generates_report_and_stops_without_claiming_complete(self):
  result,end,complete,calls=self.simulate('observation-ended.json');self.assertEqual(result,'unverified_observation_end');self.assertFalse(complete);self.assertFalse(end['capture_complete_marker']);self.assertIn(('report.py',w.BUNDLED),calls)
 def test_monitor_deadline_stops_without_manufacturing_capture_completion(self):
  result,end,complete,calls=self.simulate(deadline=100,now=100);self.assertEqual(result,'deadline_without_capture_marker');self.assertFalse(complete);self.assertIn(('report.py',w.BUNDLED),calls)
 def test_verified_capture_marker_remains_distinct_from_monitor_end(self):
  result,end,complete,calls=self.simulate('complete.json');self.assertEqual(result,'complete');self.assertTrue(complete);self.assertTrue(end['capture_complete_marker'])
if __name__=='__main__':unittest.main()
