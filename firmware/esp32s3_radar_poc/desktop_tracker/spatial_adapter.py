"""Expose the bounded spatial detector to the existing development viewer."""
from collections import deque
from pathlib import Path
import sys
from presence_tracker import PresenceTracker

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'mrs6240_custom'))
from spatial_presence import SpatialPresence

def tracker_class(model):
    class SpatialTracker(PresenceTracker):
        def __init__(self, filtered=True, use_presence=False):
            super().__init__(filtered=filtered,use_presence=use_presence)
            self.spatial=SpatialPresence(model)
            self.spatial_status=None
            self.ident=1
            self.reserve_seat(1,*model['parameters']['target_xyz'][:2])

        def reserve_seat(self, ident, x, y):
            anchor=model['parameters']['target_xyz']
            if abs(x-anchor[0])>.001 or abs(y-anchor[1])>.001:
                raise ValueError('Selected seat differs from the calibrated 3-D region')
            super().reserve_seat(ident,x,y)
            self.ident=ident
            self.focus['anchor']=tuple(anchor)
            self.spatial=SpatialPresence(model)
            self.spatial_status=None

        def focus_presence(self, ident):
            if ident not in (None,self.ident):
                raise ValueError('This model supports only its calibrated stationary region')

        def update(self, points, t, radius=.6, minimum=3, horizontal=True):
            if self.last is not None and t<=self.last:
                return self.tracks
            self.last=t
            state=self.spatial.update(dict(time_s=t,points=points))
            self.spatial_status=state
            q=self.focus['track']
            if state['accepted_now']:
                q.update(pos=list(state['center']),points=state['points'],last=t,
                         evidence_time=t,hits=q['hits']+1)
                q['trail'].append(tuple(q['pos']))
            q['state']={'fresh':'fresh spatial presence','retained':'retained location — no fresh presence','unobserved':'unobserved'}[state['state']]
            self.tracks={self.ident:q} if state['occupied'] else {}
            return self.tracks
    return SpatialTracker
