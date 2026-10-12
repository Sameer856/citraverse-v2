"""Frozen 3-D clutter envelope and bounded temporal presence evidence.

Host development implementation. Motion and retained points never refresh evidence.
"""
from collections import Counter, deque
import math


class SpatialPresence:
    def __init__(self, model):
        self.model = model
        p=model['parameters']
        if model.get('schema')!=1 or model.get('method') not in ('frozen_voxel_max_temporal_v1','frozen_voxel_max_temporal_v2'):
            raise ValueError('Unsupported spatial model')
        for key in ('x','y','radius','snr','voxel_m','window_s','minimum_bursts','minimum_points','association_m','fresh_s','retention_s'):
            if not isinstance(p.get(key),(int,float)) or not math.isfinite(p[key]):
                raise ValueError('Invalid spatial parameter: '+key)
        if not (.1<=p['fresh_s']<=.5 and p['fresh_s']<=p['retention_s']<=1.5
                and .4<=p['window_s']<=2 and 3<=p['minimum_bursts']<=10
                and .05<=p['voxel_m']<=.5 and 1<=p['minimum_points']<=256
                and .1<=p['association_m']<=.6 and .1<=p['radius']<=2):
            raise ValueError('Spatial model exceeds evidence lifetime or size bounds')
        if model['method']=='frozen_voxel_max_temporal_v2' and not (
                type(p.get('minimum_window_points')) is int and 6<=p['minimum_window_points']<=2048
                and type(p.get('strong_points')) is int and 2<=p['strong_points']<=256):
            raise ValueError('Invalid temporal evidence requirements')
        if p.get('target_xyz') is not None and (len(p['target_xyz'])!=3
                or not all(math.isfinite(v) and abs(v)<=20 for v in p['target_xyz'])
                or not .1<=p.get('target_radius_m',0)<=1):
            raise ValueError('Invalid selected 3-D region')
        self.background = {tuple(map(int, k.split(','))): v for k, v in model['background'].items()}
        self.history = deque()
        self.last_frame = None
        self.last_evidence = None
        self.center = None

    @staticmethod
    def points(row, parameters):
        unique = {}
        for p in row['points']:
            if p.get('cloud', 'presence') != 'presence':
                continue
            if not all(math.isfinite(p.get(k, float('nan'))) for k in ('x','y','z','snr')):
                continue
            if p['snr'] < parameters['snr']:
                continue
            if parameters.get('target_xyz') is not None:
                if sum((p[k]-v)**2 for k,v in zip(('x','y','z'),parameters['target_xyz']))>parameters['target_radius_m']**2:
                    continue
            elif (p['x']-parameters['x'])**2+(p['y']-parameters['y'])**2 > parameters['radius']**2:
                continue
            key = tuple(math.floor(p[k]/.02) for k in ('x','y','z'))
            unique[key] = p
        return list(unique.values())

    @staticmethod
    def voxel(p, parameters):
        return tuple(math.floor(p[k]/parameters['voxel_m']) for k in ('x','y','z'))

    @classmethod
    def calibrate(cls, rows, parameters=None):
        parameters = dict(dict(x=-.24, y=1.03, radius=.5, snr=18,
                                       voxel_m=.20, window_s=1.5, minimum_bursts=3,
                                       minimum_points=2, association_m=.35,
                                       fresh_s=.35, retention_s=1.0,
                                       minimum_window_points=6, strong_points=2), **(parameters or {}))
        if len(rows)<200 or rows[-1]['time_s']-rows[0]['time_s']<45:
            raise ValueError('Require at least 45 seconds of empty-scene training')
        background = Counter()
        last = None
        for row in rows:
            if last is not None and not 0 < row['time_s']-last <= .5:
                raise ValueError('Training contains a nonmonotonic timestamp or stream gap')
            last = row['time_s']
            counts = Counter(cls.voxel(p, parameters) for p in cls.points(row, parameters))
            for cell, n in counts.items():
                background[cell] = max(background[cell], n)
        return dict(schema=1, method='frozen_voxel_max_temporal_v2', parameters=parameters,
                    background={','.join(map(str,k)):v for k,v in sorted(background.items())},
                    training_frames=len(rows), training_seconds=rows[-1]['time_s']-rows[0]['time_s'])

    def update(self, row):
        t = row['time_s']
        p = self.model['parameters']
        if self.last_frame is not None and t<=self.last_frame:
            raise ValueError('Nonmonotonic frame timestamp')
        if self.last_frame is not None and t-self.last_frame>.5:
            self.history.clear()
            self.last_evidence = None
            self.center = None
        self.last_frame = t
        while self.history and t-self.history[0][0]>p['window_s']:
            self.history.popleft()
        cells = {}
        for point in self.points(row,p):
            cells.setdefault(self.voxel(point,p), []).append(point)
        foreground = []
        for cell, points in cells.items():
            extra = len(points)-self.background.get(cell,0)
            if extra>0:
                # Residual count is evidence, not proof of which individual return moved.
                foreground.extend(sorted(points,key=lambda q:(-q['snr'],q['x'],q['y'],q['z']))[:extra])
        # A connected compact group must repeat near itself across multiple bursts.
        groups = []
        pending = list(foreground)
        while pending:
            group = [pending.pop()]
            for point in group:
                near = [q for q in pending if sum((q[k]-point[k])**2 for k in ('x','y','z'))<=p['association_m']**2]
                for q in near:
                    pending.remove(q)
                group.extend(near)
            groups.append(group)
        groups.sort(key=lambda g:-len(g))
        accepted = []
        for group in groups:
            if len(group)<p['minimum_points']:
                continue
            center = tuple(sum(q[k] for q in group)/len(group) for k in ('x','y','z'))
            if max(sum((q[k]-center[i])**2 for i,k in enumerate(('x','y','z'))) for q in group)>p['association_m']**2:
                continue
            matches = [n for _,old,n in self.history if sum((center[i]-old[i])**2 for i in range(3))<=p['association_m']**2]
            # Append only one candidate per frame; duplicates cannot satisfy temporal birth.
            self.history.append((t,center,len(group)))
            if (len(matches)+1 >= p['minimum_bursts']
                    and sum(matches)+len(group)>=p.get('minimum_window_points',0)
                    and max(matches+[len(group)])>=p.get('strong_points',1)):
                self.last_evidence = t
                self.center = center
                accepted = group
            break
        age = t-self.last_evidence if self.last_evidence is not None else None
        fresh = age is not None and age<=p['fresh_s']
        retained = age is not None and age<=p['retention_s']
        return dict(fresh=fresh, occupied=retained,
                    state='fresh' if fresh else 'retained' if retained else 'unobserved',
                    evidence_age_s=age, accepted_now=bool(accepted),
                    residual_points=len(foreground), center=self.center,
                    points=accepted, region_id=1)


def evaluate(model, rows):
    tracker = SpatialPresence(model)
    states = [tracker.update(row) for row in rows]
    accepted = [row['time_s'] for row,state in zip(rows,states) if state['accepted_now']]
    start,end = rows[0]['time_s'],rows[-1]['time_s']
    boundaries = [start]+accepted+[end]
    return dict(frames=len(rows), duration_s=end-start,
                accepted_bursts=len(accepted), fresh_frames=sum(s['fresh'] for s in states),
                retained_or_fresh_frames=sum(s['occupied'] for s in states),
                max_evidence_gap_including_edges_s=max(b-a for a,b in zip(boundaries,boundaries[1:])),
                first_evidence_after_s=accepted[0]-start if accepted else None,
                limitation='Host callback timing; retained state is not fresh point evidence.')
