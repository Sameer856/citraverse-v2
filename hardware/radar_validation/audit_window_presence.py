"""Replay the fixed temporal seat rule; output stays beside the local capture."""
import argparse
import gzip
import json
import math
from collections import deque
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('capture', type=Path)
p.add_argument('--x', type=float, default=-.2402809604)
p.add_argument('--y', type=float, default=1.025518486)
a = p.parse_args()
opener = gzip.open if a.capture.suffix == '.gz' else open
with opener(a.capture, 'rt') as f:
    rows = [json.loads(line) for line in f if line.strip()]
history = deque()
last = previous = None
accepted = []
fresh = visible = 0
for row in rows:
    t = row['time_s']
    if previous is not None and t <= previous:
        raise ValueError('nonmonotonic capture')
    if previous is not None and t-previous > .5:
        history.clear()
    previous = t
    n = len({tuple(round(q[k],2) for k in ('x','y','z')) for q in row['points']
             if all(math.isfinite(q.get(k,float('nan'))) for k in ('x','y','z','snr'))
             and q['snr'] >= 18 and (q['x']-a.x)**2+(q['y']-a.y)**2 <= .25})
    history.append((t,n))
    while history and t-history[0][0] > 1.5:
        history.popleft()
    if n >= 2 and sum(v for _,v in history) >= 34:
        last = t
        accepted.append(t)
    age = t-last if last is not None else float('inf')
    fresh += age <= .35
    visible += age <= 2
result = dict(frames=len(rows), duration_s=rows[-1]['time_s']-rows[0]['time_s'],
              accepted_bursts=len(accepted), fresh_frames=fresh, visible_frames=visible,
              max_internal_gap_s=max((y-x for x,y in zip(accepted,accepted[1:])),default=None),
              tail_age_s=rows[-1]['time_s']-last if last is not None else None,
              rule='34 observations in 1.5 seconds plus 2 unique current points; SNR>=18; 0.5m seat',
              limitation='Cropped replay lacks prior history; selected region is not human identity')
a.capture.with_name(a.capture.name.split('.')[0]+'_window_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
