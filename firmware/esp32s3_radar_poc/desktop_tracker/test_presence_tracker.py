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

# Two observations cannot overwrite the same prior ID in one frame.
from collections import deque
from types import SimpleNamespace
def observation(x,t):
    return dict(pos=[x,1,0],points=[dict(p,x=x) for p in group('presence')],
                last=t,evidence_time=t,hits=4,state='confirmed presence cluster',trail=deque(maxlen=40))
tr=PresenceTracker()
tr.tracks={1:observation(0,0),2:observation(1,0)}
tr.next_id=3
tr.motion=SimpleNamespace(update=lambda *a,**k:{8:observation(.45,.2),9:observation(.6,.2)})
out=tr.update([],.2)
assert set(out)=={1,2}
assert out[1]['last']==out[2]['last']==.2
assert out[1]['points'][0]['x']==.45 and out[2]['points'][0]['x']==.6
assert out[1]['pos'][0]<.45 and out[2]['pos'][0]>.6
print('PASS: one-to-one prior-frame association and smoothed centers with unmodified evidence')
