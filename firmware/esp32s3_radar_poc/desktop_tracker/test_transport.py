import sys,unittest,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'build/tracker_deps'))
from transport import records
class PacketTests(unittest.TestCase):
    def test_two_records_keep_ids_times_and_payload(self):
        body=struct.pack('<BBHhhhhHH',4,1,12,100,-200,300,5,2000,0)
        one=struct.pack('<6I',0x32524452,1000,20,7,len(body)//4,0)+body
        two=struct.pack('<6I',0x32524452,1050,10,8,0,0)
        decoded=list(records(one+two));self.assertEqual(decoded,[(7,1000,20,body),(8,1050,10,b'')])
    def test_rejects_incomplete_and_bad_magic(self):
        for data in [b'bad',struct.pack('<6I',0,0,0,1,0,0),struct.pack('<6I',0x32524452,0,0,1,4,0)]:
            with self.assertRaises(ValueError):list(records(data))
if __name__=='__main__':unittest.main()
