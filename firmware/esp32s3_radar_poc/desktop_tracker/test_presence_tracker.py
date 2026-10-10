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
# A stationary presence identity can return after a short dropout, without
# displaying the old points as fresh or retaining identities indefinitely.
tr=PresenceTracker(use_presence=True)
for t in (0,.6,1.2): tr.update(group('presence'),t)
ident=next(iter(tr.tracks))
assert not tr.update([],3.3)
for t in (4,4.2,4.4): tr.update(group('presence'),t)
assert set(tr.tracks)=={ident} and tr.tracks[ident]['last']==4.4
assert not tr.update([],20)
for t in (21,21.2,21.4): tr.update(group('presence'),t)
assert ident not in tr.tracks and tr.tracks
# Two nearby dormant identities must not be arbitrarily reassigned.
tr=PresenceTracker()
tr.dormant={1:observation(0,0),2:observation(.1,0)}
tr.next_id=3
tr.motion=SimpleNamespace(update=lambda *a,**k:{8:observation(.05,4)})
assert set(tr.update([],4))=={3}
print('PASS: bounded presence reacquisition, expiry and ambiguous identity rejection')
# New evidence outside the stationary recovery gate must get a new ID.
tr=PresenceTracker()
tr.dormant={1:observation(0,0)}
tr.next_id=2
tr.motion=SimpleNamespace(update=lambda *a,**k:{8:observation(.5,4)})
assert set(tr.update([],4))=={2}
# Motion observations cannot reclaim an old presence identity.
tr=PresenceTracker()
tr.dormant={1:observation(0,0)}
tr.next_id=2
q=observation(0,4)
q['points']=[dict(p,cloud='motion') for p in q['points']]
tr.motion=SimpleNamespace(update=lambda *a,**k:{8:q})
assert set(tr.update([],4))=={2}
print('PASS: distant returns and motion cannot reclaim presence identities')
# A selected stationary region cannot be pulled away by a neighboring cluster.
tr=PresenceTracker(use_presence=True)
for t in (0,.6,1.2): tr.update(group('presence'),t)
ident=next(iter(tr.tracks))
tr.focus_presence(ident)
anchor=tr.focus['anchor']
near=[dict(p,x=p['x']+.1) for p in group('presence')]
far=[dict(p,x=p['x']+1.1) for p in group('presence')]
tr.update(near+far,1.4)
assert ident in tr.tracks and tr.tracks[ident]['last']==1.4
assert all((p['x']-anchor[0])**2+(p['y']-anchor[1])**2<=.5**2 for p in tr.tracks[ident]['points'])
assert ident not in tr.update(far,4)
assert tr.focus['track']['last']==1.4
assert ident in tr.update(near,25)  # Reserved seat label, new evidence only.
assert tr.tracks[ident]['last']==25
tr.focus_presence(None)
assert tr.focus is None
print('PASS: stationary region selection, neighboring exclusion, true absence and fresh return')
