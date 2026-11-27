"""Run with a vendor rawData.bin capture as the first argument."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'live_tracker'))
from protocol import Stream
from devkit_feed import RecordingDecoder

data=Path(sys.argv[1]).read_bytes()
expected=RecordingDecoder(Stream()).feed(data)
assert expected, 'Capture must contain point-cloud frames'
decoder=RecordingDecoder(Stream())
actual=[]
for i in range(0,len(data),37):
    actual.extend(decoder.feed(data[i:i+37]))
assert actual==expected, 'Partial file writes changed decoded frames'
assert all('host_timestamp_ms' in f for f in actual)
assert {'motion','presence'} <= {p['cloud'] for f in actual for p in f['points']}
assert not decoder.stats['checksum_errors']
print(f'Passed: {len(actual)} frames, partial writes, timestamps, both cloud types')
