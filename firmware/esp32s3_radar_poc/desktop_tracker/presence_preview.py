"""Hold only the most recent presence burst for display, never for detection."""
class PresencePreview:
    def __init__(self):
        self.points=[]
        self.updated=None
        self.last=None
    def update(self, points, t):
        if self.last is not None and (t<=self.last or t-self.last>.35):
            self.points=[]; self.updated=None
        self.last=t
        if points:
            self.points=list(points); self.updated=t
        if self.updated is None or t-self.updated>.35:
            self.points=[]
        return self.points, None if not self.points else t-self.updated
