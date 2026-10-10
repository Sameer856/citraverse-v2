"""Burst-tolerant presence evidence; retained tracks are never fresh fall samples."""
import math
from collections import deque
from human_presence import HumanTracker as MotionTracker
from protocol import Tracker as Clusterer


class PresenceTracker:
    def __init__(self, filtered=True, use_presence=False):
        self.motion = MotionTracker(filtered=filtered, use_presence=False)
        self.base = self.motion.base
        self.use_presence = use_presence
        self.tracks = {}
        self.pending = {}
        self.dormant = {}
        self.next_id = 1
        self.last = None
        self.focus = None

    def focus_presence(self, ident):
        """Reserve a stationary selected seat; never claim evidence in an empty ROI."""
        if ident is None:
            self.focus = None
        elif self.focus is None or self.focus['id'] != ident:
            q = self.tracks.get(ident)
            if q and all(p.get('cloud') == 'presence' for p in q['points']):
                self.focus = dict(id=ident, anchor=tuple(q['pos']), track=dict(q))

    def update(self, points, t, radius=.6, minimum=3, horizontal=True):
        if self.last is not None and t <= self.last:
            return self.tracks
        self.last = t
        # Keep bounded identity memory separately from visible/fresh detections.
        self.dormant.update({i:q for i,q in self.tracks.items() if t-q['last'] > 2})
        self.dormant = {i:q for i,q in self.dormant.items() if 0 <= t-q['last'] <= 15}
        self.tracks = {i:q for i,q in self.tracks.items() if 0 <= t-q['last'] <= 2}
        self.pending = {i:q for i,q in self.pending.items() if 0 <= t-q['last'] <= 2}
        focus_points = []
        if self.focus is not None and self.use_presence:
            anchor = self.focus['anchor']
            unique = {}
            remaining = []
            for p in points:
                inside = (p.get('cloud') == 'presence'
                          and all(math.isfinite(p.get(k,float('nan'))) for k in ('x','y','z','snr'))
                          and sum((p[k]-anchor[n])**2 for n,k in enumerate(('x','y'))) <= .5**2)
                if inside:
                    if p['snr'] >= 18:
                        unique[tuple(round(p[k],2) for k in ('x','y','z'))] = p
                else:
                    remaining.append(p)
            focus_points = list(unique.values())
            points = remaining
            # Reserve the identity so other room clusters cannot pull its center.
            self.tracks.pop(self.focus['id'],None)
            self.dormant.pop(self.focus['id'],None)
        observations = [q for q in self.motion.update(points,t,radius,minimum).values() if q['last']==t]
        if self.use_presence:
            # Presence is allowed to be sparse, but duplicates/isolated returns cannot seed.
            unique = {}
            for p in points:
                if p.get('cloud') != 'presence': continue
                if not all(math.isfinite(p.get(k,float('nan'))) for k in ('x','y','z','snr')): continue
                if p['snr'] < 18: continue
                unique[tuple(round(p[k],2) for k in ('x','y','z'))] = p
            clusters = Clusterer()
            clusters.update(list(unique.values())[:1024],t,radius,3,horizontal=True)
            used = set()
            for q in clusters.tracks.values():
                if any(max(p[k] for p in q['points'])-min(p[k] for p in q['points'])>2.5 for k in ('x','y')): continue
                near = sorted((sum((q['pos'][k]-e['pos'][k])**2 for k in range(2)),i) for i,e in self.pending.items() if i not in used)
                ident = near[0][1] if near and near[0][0]<=radius**2 else self.next_id
                if ident == self.next_id: self.next_id += 1
                e = self.pending.setdefault(ident,dict(times=deque()))
                e.update(pos=q['pos'],last=t)
                e['times'].append(t)
                while e['times'] and t-e['times'][0]>2: e['times'].popleft()
                used.add(ident)
                established = any(sum((q['pos'][k]-a['pos'][k])**2 for k in range(2)) <= radius**2
                                  for a in self.tracks.values())
                if established or (len(e['times'])>=3 and t-e['times'][0]>=.1-1e-8):
                    observations.append(dict(q,state='confirmed presence cluster'))
        # Match against one immutable prior-frame snapshot. Previously an observation
        # could move an ID, then another cluster could reuse that same ID in this frame.
        pairs = sorted((sum((q['pos'][k]-e['pos'][k])**2 for k in range(2)),i,j)
                       for i,e in self.tracks.items() for j,q in enumerate(observations))
        assigned = {}; used = set()
        for distance,i,j in pairs:
            if distance>radius**2 or i in used or j in assigned: continue
            assigned[j]=i; used.add(i)
        # Reacquire only mutually unambiguous nearby dormant presence tracks.
        # An absence remains an absence; this restores an ID only on new evidence.
        candidates = {j:[i for i,e in self.dormant.items()
                         if all(p.get('cloud') == 'presence' for p in q['points'])
                         and all(p.get('cloud') == 'presence' for p in e['points'])
                         and sum((q['pos'][k]-e['pos'][k])**2 for k in range(2)) <= .35**2]
                      for j,q in enumerate(observations) if j not in assigned}
        for j,ids in candidates.items():
            if len(ids)==1 and sum(ids[0] in v for v in candidates.values())==1:
                ident=ids[0]
                assigned[j]=ident
                self.tracks[ident]=self.dormant.pop(ident)
        used = set()
        for j,q in enumerate(observations):
            ident = assigned.get(j)
            if ident is None:
                ident=self.next_id; self.next_id+=1
            e = self.tracks.setdefault(ident,dict(trail=deque(maxlen=40)))
            # Smooth the association center, not the current point cloud or its time.
            position=[.7*a+.3*b for a,b in zip(e['pos'],q['pos'])] if 'pos' in e else list(q['pos'])
            e.update(pos=position,points=list(q['points']),last=t,evidence_time=t,hits=q['hits'],state=q['state'])
            e['trail'].append(tuple(e['pos']))
            used.add(ident)
        for i,q in self.tracks.items():
            if i not in used: q['state']='temporarily unobserved'
        if self.focus is not None and self.use_presence:
            q = self.focus['track']
            if len(focus_points) >= 3:
                q.update(pos=[sum(p[k] for p in focus_points)/len(focus_points) for k in ('x','y','z')],
                         points=focus_points,last=t,evidence_time=t,
                         hits=q['hits']+1,state='selected stationary presence region')
                q['trail'].append(tuple(q['pos']))
            else:
                q['state']='temporarily unobserved'
            if 0 <= t-q['last'] <= 2:
                self.tracks[self.focus['id']] = q
        return self.tracks
