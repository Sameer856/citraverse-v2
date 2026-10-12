"""Freeze a model from the first 60 seconds and evaluate separate captures."""
import argparse
import json
from pathlib import Path
from spatial_presence import SpatialPresence, evaluate

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--empty',type=Path,required=True)
    parser.add_argument('--seated',type=Path,required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--target',type=float,nargs=3)
    parser.add_argument('--target-radius',type=float,default=.35)
    parser.add_argument('--minimum-points',type=int,choices=(1,2),default=2,
                        help='Current residual points; temporal acquisition still requires multi-point evidence')
    args=parser.parse_args()
    rows=read(args.empty)
    start=rows[0]['time_s']
    train=[r for r in rows if r['time_s']-start<60]
    holdout=[r for r in rows if r['time_s']-start>=60]
    if not holdout or holdout[-1]['time_s']-holdout[0]['time_s']<25:
        raise ValueError('Need at least 25 seconds of untouched empty holdout')
    parameters=dict(target_xyz=args.target,target_radius_m=args.target_radius,retention_s=1.2,
                    minimum_points=args.minimum_points) if args.target else dict(minimum_points=args.minimum_points)
    model=SpatialPresence.calibrate(train,parameters)
    args.model.write_text(json.dumps(model,indent=2))
    result=dict(model_cells=len(model['background']),
                training= evaluate(model,train),
                empty_holdout=evaluate(model,holdout),
                seated_development=evaluate(model,read(args.seated)))
    args.model.with_suffix('.evaluation.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
