import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[4]/'live_tracker'))
from presence_tracker import PresenceTracker
from test_target_filter import group

tr = PresenceTracker(use_presence=True)
for t in (0,.6,1.2): tr.update(group('presence'),t)
assert len(tr.tracks)==1
ident=next(iter(tr.tracks))
assert tr.tracks[ident]['last']==1.2
tr.update([],1.5)
assert tr.tracks[ident]['last']==1.2  # Never invent a current height sample.
assert tr.tracks[ident]['state']=='temporarily unobserved'
assert not tr.update([],3.3)
for pts in ([group('presence')[0]]*8, group('presence')[:2], [dict(p,snr=5) for p in group('presence')]):
    tr=PresenceTracker(use_presence=True)
    for t in (0,.6,1.2): assert not tr.update(pts,t)
tr=PresenceTracker(use_presence=False)
for t in (0,.6,1.2): assert not tr.update(group('presence'),t)
tr=PresenceTracker(use_presence=True)
for t in (0,3,6): assert not tr.update(group('presence'),t)
print('PASS: intermittent presence, expiration, stale evidence, duplicate/sparse/weak rejection, motion-only isolation')
