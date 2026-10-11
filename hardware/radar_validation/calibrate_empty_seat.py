"""Build a fixed density gate from an explicitly confirmed empty-seat capture.

First 60 seconds train; next 30 seconds are held out. Never run on occupied data.
This calibrates a selected region, not a human classifier or the radar firmware.
"""
import argparse
import gzip
import json
import math
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('capture', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--x', type=float, required=True)
p.add_argument('--y', type=float, required=True)
p.add_argument('--confirmed-empty', action='store_true', required=True)
a = p.parse_args()
if not all(math.isfinite(v) for v in (a.x, a.y)):
    p.error('anchor must be finite')
opener = gzip.open if a.capture.suffix == '.gz' else open
with opener(a.capture, 'rt', encoding='utf-8') as f:
    rows = [json.loads(line) for line in f if line.strip()]
if not rows:
    p.error('no frames')
start = rows[0]['time_s']
if rows[-1]['time_s'] - start < 89.9:
    p.error('at least 90 seconds of confirmed empty-room capture required')
if any(y['time_s'] <= x['time_s'] or y['time_s'] - x['time_s'] > .5
       for x, y in zip(rows, rows[1:])):
    p.error('nonmonotonic timestamps or capture gap over 500 ms')

def count(row):
    return len({tuple(round(q[k], 2) for k in ('x', 'y', 'z'))
                for q in row['points']
                if all(math.isfinite(q.get(k, float('nan'))) for k in ('x', 'y', 'z', 'snr'))
                and q['snr'] >= 18
                and (q['x']-a.x)**2 + (q['y']-a.y)**2 <= .5**2})

train = [r for r in rows if 0 <= r['time_s']-start < 60]
test = [r for r in rows if 60 <= r['time_s']-start <= 90]
if not any(r['points'] for r in train) or not any(r['points'] for r in test):
    p.error('no presence bursts; cannot distinguish missing data from an empty room')
minimum = max(3, max(map(count, train))+1)
if minimum > 256:
    p.error('no usable threshold below the sensor point limit')
model = dict(method='fixed_empty_seat_max_plus_one_v1', anchor=[a.x, a.y],
             radius_m=.5, snr_min=18, minimum_points=minimum,
             training_seconds=60, training_frames=len(train), holdout_frames=len(test),
             holdout_accepted_frames=sum(count(r) >= minimum for r in test),
             holdout_max_points=max(map(count, test)),
             warning='Experimental region density gate; not person identity; never adapts online')
a.output.write_text(json.dumps(model, indent=2)+'\n')
print(json.dumps(model, indent=2))
