import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'live_tracker'))
from spatial_adapter import SpatialPresence, tracker_class

point=dict(x=-.24,y=1.03,z=.4,snr=25,cloud='presence')
rows=[dict(time_s=i*.1,points=[]) for i in range(601)]
model=SpatialPresence.calibrate(rows,dict(target_xyz=[-.24,1.03,.4],target_radius_m=.35))
tracker=tracker_class(model)(use_presence=True)
points=[point,dict(point,x=-.18)]
for t in (0,.2,.4):tracker.update(points,t)
assert set(tracker.tracks)=={1}
last=tracker.tracks[1]['last']
tracker.update([],.8)
assert tracker.tracks[1]['last']==last
assert 'retained' in tracker.tracks[1]['state']
tracker.update([],1.2)
assert not tracker.update([],1.5)
for t in (1.6,1.8,2.):tracker.update(points,t)
assert set(tracker.tracks)=={1}
try:tracker.reserve_seat(1,0,0)
except ValueError:pass
else:raise AssertionError('mismatched region accepted')
print('PASS: spatial viewer ID, non-refreshed retained timestamps, expiry, reacquisition, region match')
