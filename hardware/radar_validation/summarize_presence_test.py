"""Summarize one-second tracker snapshots; this is not per-frame identity proof."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('capture', type=Path)
parser.add_argument('--target', default='3')
args = parser.parse_args()
rows = json.loads(args.capture.read_text(encoding='utf-8-sig'))
present = [r for r in rows if args.target in r['state']['tracks']]
ages = sorted(r['state']['tracks'][args.target]['age_s'] for r in present)
first, last = rows[0], rows[-1]
a, b = first['state'], last['state']
summary = dict(target='T'+args.target, samples=len(rows),
    duration_s=last['elapsed_s']-first['elapsed_s'],
    distinct_snapshots=len({r['state']['frame'] for r in rows}),
    present=len(present), missing=len(rows)-len(present),
    fresh_within_350ms=sum(x<=.35 for x in ages),
    max_evidence_age_s=max(ages,default=None),
    first_missing_s=next((r['elapsed_s'] for r in rows if args.target not in r['state']['tracks']),None),
    presence_only_mode=all(r['state']['presence_only_tracking'] for r in rows),
    presence_only_evidence=bool(present) and all(r['state']['tracks'][args.target]['clouds']==['presence'] for r in present),
    selected_throughout=all(r['state'].get('selected_target')=='T'+args.target for r in rows),
    saved_state_span_s=b.get('saved_at',0)-a.get('saved_at',0),
    max_snapshot_update_gap_s=max((q['state'].get('saved_at',0)-p['state'].get('saved_at',0) for p,q in zip(rows,rows[1:])),default=0),
    position_bounds={k:[min(r['state']['tracks'][args.target]['position'][i] for r in present),max(r['state']['tracks'][args.target]['position'][i] for r in present)] for i,k in enumerate('xyz')} if present else {},
    stationary_focus_anchor=a.get('stationary_focus_anchor'),
    callback_fps=b['stats'].get('callback_fps'),
    counter_deltas={k:b['stats'].get(k,0)-a['stats'].get(k,0) for k in ('frames','presence_points','nonconsecutive','queue_drops','stale_frames')},
    limitation='One-second state samples; selected stationary region is not independently verified human identity.')
args.capture.with_name(args.capture.stem+'_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
