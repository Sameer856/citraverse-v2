"""Summarize vendor RadarDebugTool frame-info CSV without assuming timing units."""
import csv
import json
import sys
from pathlib import Path
from collections import Counter

path = Path(sys.argv[1])
rows = list(csv.reader(path.open(encoding='utf-8-sig')))
rows = [r for r in rows if len(r) == 13]
times = [int(r[1]) for r in rows]
indices = [int(r[2]) for r in rows]
deltas = [(b-a) & 0xffff for a,b in zip(indices, indices[1:])]
intervals = sorted(b-a for a,b in zip(times,times[1:]))
result = {
    'source': path.name, 'rows': len(rows),
    'host_timestamp_span_seconds': (times[-1]-times[0])/1000,
    'received_fps': (len(rows)-1)*1000/(times[-1]-times[0]),
    'first_index': indices[0], 'last_index': indices[-1],
    'duplicates': deltas.count(0),
    'forward_missing_indices': sum(d-1 for d in deltas if 1 < d < 0x8000),
    'backward_or_reset_transitions': sum(d >= 0x8000 for d in deltas),
    'host_interval_ms': {'min': min(intervals), 'median': intervals[len(intervals)//2],
                         'p99': intervals[int((len(intervals)-1)*.99)], 'max': max(intervals)},
    'columns_3_to_8_unique': [dict(Counter(r[i] for r in rows)) for i in range(3,9)],
    'diagnostics': {name: {
        'min': min(float(r[i]) for r in rows), 'max': max(float(r[i]) for r in rows),
        'mean': sum(float(r[i]) for r in rows)/len(rows)}
        for i,name in enumerate(['processing_duration_raw_sdk_comment_0p1ms',
                                  'minimum_ever_free_heap_KiB', 'motion_points', 'presence_points'],9)},
    'limitations': 'Host arrival timestamps, not electrical frame timing. Scene occupancy unknown. No fall accuracy inference.'
}
print(json.dumps(result, indent=2))
