import unittest
import jetscan
import numpy as np


class GeometryTests(unittest.TestCase):
    def test_pair_timing(self):
        self.assertTrue(jetscan.matched(1, 1.019))
        self.assertFalse(jetscan.matched(1, 1.021))

    def test_pose_direction_with_rotation(self):
        previous = np.eye(4)
        previous[:3, 3] = [1, 2, 3]
        relative = np.array([[0., -1, 0, 0.1], [1, 0, 0, 0],
                             [0, 0, 1, 0], [0, 0, 0, 1]])
        point_previous = np.array([0.2, 0.4, 1, 1])
        point_current = relative @ point_previous
        new_pose = jetscan.camera_to_world(previous, relative)
        np.testing.assert_allclose(new_pose @ point_current, previous @ point_previous)

    def test_tracking_rejects_jump_nan_and_rotation(self):
        information = np.eye(6)
        transform = np.eye(4)
        self.assertTrue(jetscan.acceptable(transform, information))
        transform[0, 3] = 0.3
        self.assertFalse(jetscan.acceptable(transform, information))
        transform = np.diag([-1., -1, 1, 1])
        self.assertFalse(jetscan.acceptable(transform, information))
        transform[0, 0] = np.nan
        self.assertFalse(jetscan.acceptable(transform, information))


if __name__ == '__main__':
    unittest.main()
