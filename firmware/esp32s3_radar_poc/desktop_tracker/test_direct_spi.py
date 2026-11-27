import base64
import io
import json
import sys
import types
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'live_tracker'))
from protocol import points
from direct_spi import DirectSpi

capture=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
callbacks=[c for c in capture['callbacks'] if c['data_type']==4]
feed=DirectSpi.__new__(DirectSpi)
feed.stats=Counter();feed.decode=points;feed.last_index=None;feed.first_time=None;feed.last_time=None
lines=[json.dumps(dict(frame=c['frame_index'],words=c['frame_length'],
    timestamp_ms=1700000000000+round(c['elapsed_s']*1000),data=c['payload_base64'])) for c in callbacks]
feed.process=types.SimpleNamespace(stdout=io.StringIO('\n'.join(lines)+'\n'))
frames=[feed.read_frames()[0] for _ in lines]
assert len(frames)==len(callbacks)>0
assert not feed.stats['duplicates'] and not feed.stats['nonconsecutive']
bad=dict(frame=1,words=1,timestamp_ms=1700000000000,data=base64.b64encode(b'').decode())
feed.process.stdout=io.StringIO(json.dumps(bad)+'\n')
try:feed.read_frames()
except ValueError:pass
else:raise AssertionError('Bad callback length accepted')
print(f'Passed {len(frames)} callback frames, continuity, payload validation')
