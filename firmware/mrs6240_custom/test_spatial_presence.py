import unittest
from spatial_presence import SpatialPresence, evaluate

def point(x=-.24, y=1.03, z=0, cloud='presence'):
    return dict(x=x,y=y,z=z,snr=25,cloud=cloud)

def row(t, points):
    return dict(time_s=t,points=points)

class SpatialTests(unittest.TestCase):
    def setUp(self):
        self.empty=[row(i*.1,[point(z=-.8)]) for i in range(601)]
        self.model=SpatialPresence.calibrate(self.empty)
    def test_background_and_duplicates(self):
        tracker=SpatialPresence(self.model)
        for i in range(30):
            state=tracker.update(row(i*.1,[point(z=-.8)]*40))
            self.assertFalse(state['occupied'])
        self.assertFalse(evaluate(self.model,self.empty)['accepted_bursts'])
    def test_temporal_freshness_and_expiry(self):
        tracker=SpatialPresence(self.model)
        points=[point(z=.4),point(x=-.18,z=.4)]
        self.assertFalse(tracker.update(row(0,points))['occupied'])
        self.assertFalse(tracker.update(row(.2,points))['occupied'])
        self.assertTrue(tracker.update(row(.4,points))['fresh'])
        self.assertEqual(tracker.update(row(.8,[]))['state'],'retained')
        tracker.update(row(1.2,[]))
        self.assertFalse(tracker.update(row(1.5,[]))['occupied'])
    def test_gap_resets_and_motion_does_not_count(self):
        tracker=SpatialPresence(self.model)
        points=[point(z=.4),point(x=-.18,z=.4)]
        for i in range(3):tracker.update(row(i*.2,points))
        self.assertFalse(tracker.update(row(1.1,points))['occupied'])
        for i in range(3):
            self.assertFalse(tracker.update(row(1.2+i*.1,[point(cloud='motion')]*10))['fresh'])
    def test_invalid_training_and_spatial_mismatch(self):
        with self.assertRaises(ValueError):SpatialPresence.calibrate(self.empty[:10])
        broken=list(self.empty);broken[4]=row(9,[])
        with self.assertRaises(ValueError):SpatialPresence.calibrate(broken)
        tracker=SpatialPresence(self.model)
        for i in range(3):
            z=i*.8
            self.assertFalse(tracker.update(row(i*.2,[point(z=z),point(x=-.18,z=z)]))['occupied'])
    def test_single_points_never_acquire_or_sustain_forever(self):
        self.model['parameters']['minimum_points']=1
        tracker=SpatialPresence(self.model)
        for i in range(30):
            self.assertFalse(tracker.update(row(i*.2,[point(z=.4)]))['occupied'])
        for i in range(3):tracker.update(row(6+i*.2,[point(z=.4),point(x=-.18,z=.4)]))
        for i in range(20):state=tracker.update(row(6.6+i*.2,[point(z=.4)]))
        self.assertFalse(state['occupied'])
    def test_model_cannot_enable_indefinite_retention(self):
        self.model['parameters']['retention_s']=10
        with self.assertRaises(ValueError):SpatialPresence(self.model)

if __name__=='__main__':unittest.main()
