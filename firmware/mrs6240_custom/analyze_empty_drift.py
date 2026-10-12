"""Compare old calibration with a later labelled empty scene; never deploy changes."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from spatial_presence import SpatialPresence
from experiment_spatial import replay


def read(path):
    data = path.read_bytes()
    return [json.loads(line) for line in data.splitlines()], hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--empty', type=Path, required=True)
    parser.add_argument('--seated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = json.loads(args.model.read_text())
    empty, empty_hash = read(args.empty)
    seated, seated_hash = read(args.seated)
    start = empty[0]['time_s']
    training = [r for r in empty if r['time_s']-start < 120]
    heldout = [r for r in empty if r['time_s']-start >= 120]
    if not heldout or heldout[-1]['time_s']-heldout[0]['time_s'] < 120:
        raise ValueError('Require at least 120 seconds of empty holdout after 120-second training')
    result = dict(empty_sha256=empty_hash,seated_sha256=seated_hash,
                  limitation='Later-empty temporal holdout and retrospective seated replay; not a new occupied validation.',
                  training_frames=len(training),heldout_frames=len(heldout),variants={})
    for size in (.1,.2,.3):
        parameters=copy.deepcopy(model['parameters'])
        parameters['voxel_m']=size
        candidate=SpatialPresence.calibrate(training,parameters)
        result['variants'][str(size)] = dict(background_cells=len(candidate['background']),
            empty=replay(candidate,heldout),seated=replay(candidate,seated))
    result['original_model_empty']=replay(model,empty)
    def cells(rows):
        counts=Counter()
        for row in rows:
            counts.update(SpatialPresence.voxel(p,model['parameters'])
                          for p in SpatialPresence.points(row,model['parameters']))
        return counts
    ec,sc=cells(training),cells(seated)
    result['spatial_overlap'] = dict(
        seated_points=sum(sc.values()),
        seated_points_in_cells_seen_empty=sum(n for k,n in sc.items() if k in ec),
        empty_cells=len(ec), seated_cells=len(sc), shared_cells=len(set(ec)&set(sc)))
    with args.output.open('x') as output:
        json.dump(result,output,indent=2)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
