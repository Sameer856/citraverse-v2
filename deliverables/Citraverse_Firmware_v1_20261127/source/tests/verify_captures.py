"""Exercise the actual C parser DLL against saved vendor callback payloads."""
import base64, ctypes, json, struct, sys
from pathlib import Path
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root/'hardware/radar_validation'))
from parse_example import cartesian_points
class Info(ctypes.Structure):
    _fields_=[(n,ctypes.c_uint32) for n in ('index','motion','presence','payload_bytes')]
dll=ctypes.CDLL(str(Path(sys.argv[1]).resolve()))
parse=dll.radar_parse_c3
parse.argtypes=[ctypes.POINTER(ctypes.c_uint8),ctypes.c_size_t,ctypes.POINTER(Info)]
parse.restype=ctypes.c_bool
checked=0
for name in ('spi_vendor_capture.json','spi_41ms_reporting_capture.json','spi_restored_capture.json','spi_usb_only_60s.json'):
    capture=json.loads((root/'hardware/radar_validation'/name).read_text(encoding='utf-8-sig'))
    for frame in capture['callbacks']:
        if frame['data_type']!=4: continue
        payload=base64.b64decode(frame['payload_base64'],validate=True)
        packet=struct.pack('<III',frame['frame_index'],frame['frame_length'],0)+payload
        raw=(ctypes.c_uint8*len(packet)).from_buffer_copy(packet);info=Info()
        assert parse(raw,len(packet),ctypes.byref(info)), (name,frame['frame_index'])
        points=cartesian_points(payload)
        assert info.index==frame['frame_index'] and info.payload_bytes==len(payload)
        assert info.motion==sum(p['cloud']=='motion' for p in points)
        assert info.presence==sum(p['cloud']=='presence' for p in points)
        checked+=1
print(f'C parser matched {checked} captured frames against the independent Python decoder')
