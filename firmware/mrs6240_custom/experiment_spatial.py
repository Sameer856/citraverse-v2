"""Replay frozen spatial variants; outputs are local development evidence only."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from spatial_presence import SpatialPresence


def replay(model, rows):
    detector = SpatialPresence(model)
    first = None
    counts = dict(fresh=0, retained=0, unobserved=0)
    gaps = []
    gap_start = None
    accepted = []
    for row in rows:
        t = row['time_s']
        state = detector.update(row)
        counts[state['state']] += 1
        if state['accepted_now']:
            accepted.append(t)
        if state['occupied']:
            if first is None:
                first = t
            if gap_start is not None:
                gaps.append(t-gap_start)
                gap_start = None
        elif first is not None and gap_start is None:
            gap_start = t
    if gap_start is not None:
        gaps.append(rows[-1]['time_s']-gap_start)
    return dict(frames=len(rows), duration_s=rows[-1]['time_s']-rows[0]['time_s'],
                states=counts, first_acquisition_s=None if first is None else first-rows[0]['time_s'],
                accepted_bursts=len(accepted), post_acquisition_gaps=len(gaps),
                longest_tracking_gap_s=max(gaps, default=0),
                longest_evidence_gap_s=max((b-a for a,b in zip(accepted,accepted[1:])),default=None))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--captures', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = json.loads(args.model.read_text())
    variants = [('frozen_baseline', {})]
    variants += [('retention_'+str(ms), dict(retention_s=ms/1000)) for ms in (350,700,1000)]
    variants += [('window_'+str(ms), dict(window_s=ms/1000)) for ms in (750,1000,2000)]
    variants += [('evidence_'+str(n), dict(minimum_window_points=n)) for n in (8,10)]
    results = dict(model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                   limitation='Retrospective sensitivity analysis, not new independent validation. No deployment selection is automatic.',
                   captures={})
    for path in args.captures:
        raw = path.read_bytes()
        rows = [json.loads(line) for line in raw.splitlines()]
        out = dict(sha256=hashlib.sha256(raw).hexdigest(), variants={})
        for name, parameters in variants:
            candidate = copy.deepcopy(model)
            candidate['parameters'].update(parameters)
            out['variants'][name] = dict(changes=parameters, result=replay(candidate,rows))
        results['captures'][path.name] = out
    with args.output.open('x') as stream:
        json.dump(results,stream,indent=2)
    print(args.output)


if __name__ == '__main__':
    main()
