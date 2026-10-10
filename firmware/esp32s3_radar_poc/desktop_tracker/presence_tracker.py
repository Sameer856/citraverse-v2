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
        self.next_id = 1
        self.last = None

    def update(self, points, t, radius=.6, minimum=3, horizontal=True):
        if self.last is not None and t <= self.last:
            return self.tracks
        self.last = t
        self.tracks = {i:q for i,q in self.tracks.items() if 0 <= t-q['last'] <= 2}
        self.pending = {i:q for i,q in self.pending.items() if 0 <= t-q['last'] <= 2}
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
                if len(e['times'])>=3 and t-e['times'][0]>=.1-1e-8:
                    observations.append(dict(q,state='confirmed presence cluster'))
        used = set()
        for q in observations:
            near = sorted((sum((q['pos'][k]-e['pos'][k])**2 for k in range(2)),i) for i,e in self.tracks.items())
            ident = near[0][1] if near and near[0][0]<=radius**2 else self.next_id
            if ident == self.next_id: self.next_id += 1
            e = self.tracks.setdefault(ident,dict(trail=deque(maxlen=40)))
            members = q['points'] + (e['points'] if ident in used else [])
            e.update(pos=list(q['pos']),points=members,last=t,evidence_time=t,hits=q['hits'],
                     state='confirmed mixed cluster' if len({p['cloud'] for p in members})>1 else q['state'])
            e['trail'].append(tuple(e['pos']))
            used.add(ident)
        for i,q in self.tracks.items():
            if i not in used: q['state']='temporarily unobserved'
        return self.tracks
