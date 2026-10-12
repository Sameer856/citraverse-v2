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

# Sparse continuation uses new evidence, not persistence of old points.
tr=PresenceTracker(use_presence=True)
tr.reserve_seat(3,0,1)
pts=[dict(x=x,y=1,z=0,snr=20,cloud='presence') for x in (-.1,0,.1)]
assert not tr.update(pts[:2],0)  # Two cannot create occupancy.
assert 3 in tr.update(pts,.2)
assert tr.update(pts[:2],.4)[3]['last']==.4
assert len(tr.tracks[3]['points'])==2
tr.update(pts[:1],.6)
assert tr.tracks[3]['last']==.4
tr.update(pts[:2],1.1)
assert tr.tracks[3]['last']==.4  # Old target needs full reacquisition.
assert 3 not in tr.update([],2.5)
assert tr.update(pts,2.7)[3]['last']==2.7
print('PASS: sparse fresh continuation with strict birth/reacquisition and no single-point refresh')

# Fixed empty-seat gate never lowers for continuation and never learns occupants.
tr=PresenceTracker(use_presence=True)
tr.reserve_seat(3,0,1)
tr.background_minimum=7
tr.background_anchor=(0,1)
def seat_points(n):
    return [dict(x=.01*i,y=1,z=0,snr=25,cloud='presence',velocity=0) for i in range(n)]
assert 3 not in tr.update(seat_points(6),0)
assert 3 in tr.update(seat_points(7),.2)
tr.update(seat_points(6),.4)
assert tr.tracks[3]['last']==.2
assert 3 not in tr.update(seat_points(6),2.3)
assert 3 in tr.update(seat_points(7),2.5)
assert tr.background_minimum==7
print('PASS: fixed background gate, no sparse bypass, expiry and fresh reacquisition')

# Temporal context may classify fresh weak points, never empty/single returns.
tr=PresenceTracker(use_presence=True)
tr.reserve_seat(3,0,1)
tr.background_anchor=(0,1);tr.background_minimum=10;tr.background_window=1.5
tr.update(seat_points(8),0)
assert 3 not in tr.tracks
tr.update(seat_points(2),.2)
assert tr.tracks[3]['last']==.2
assert len(tr.tracks[3]['points'])==2
tr.update([], .4);tr.update(seat_points(1),.6)
assert tr.tracks[3]['last']==.2
tr.update(seat_points(2),1.2)  # transport gap clears context
assert tr.tracks[3]['last']==.2
assert 3 not in tr.update([],2.3)
assert sum(n for _,n in tr.background_counts)==0
print('PASS: temporal context requires fresh points, does not retimestamp history, clears on gaps')

tr=PresenceTracker(use_presence=True)
tr.reserve_seat(3,0,1)
tr.background_anchor=(0,1);tr.background_minimum=34;tr.background_window=1.5;tr.background_weak=26
for i in range(8): tr.update(seat_points(4),i*.2)
assert 3 not in tr.tracks  # weak empty background cannot start a track
tr.update(seat_points(10),1.6)
assert tr.background_strong_time==1.6
for i in range(9,50): tr.update(seat_points(4),i*.2)
assert 3 not in tr.tracks  # weak returns cannot sustain an established track forever
assert tr.background_strong_time <= 3
tr.reserve_seat(3,0,1)
assert tr.background_strong_time is None
print('PASS: weak evidence cannot acquire or perpetually sustain; reselection clears confirmation')
