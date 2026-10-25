"""Analytic RGB-D moving-camera reconstruction and exported metric geometry test."""
import argparse
import json
import tempfile
from pathlib import Path
import jetscan
import numpy as np
import open3d as o3d


def main():
    width, height = 160, 120
    k = np.array([[140., 0, 79.5], [0, 140., 59.5], [0, 0, 1.]])
    yy, xx = np.mgrid[:height, :width]
    dx = (xx-k[0, 2])/k[0, 0]
    dy = (yy-k[1, 2])/k[1, 1]
    with tempfile.TemporaryDirectory(prefix='jetscan-test-') as temporary:
        root = Path(temporary)
        frames = []
        for index in range(5):
            origin_x = index * 0.004
            z = np.ones((height, width))
            for _ in range(15):
                world_x = origin_x + dx*z
                world_y = dy*z
                z = 1 + 0.08*np.sin(9*world_x)*np.cos(8*world_y)
            color = np.stack([127+100*np.sin(34*world_x),
                              127+100*np.sin(29*world_y),
                              127+100*np.cos(23*(world_x+world_y))], axis=2).astype(np.uint8)
            name = '{:06d}.npz'.format(index)
            np.savez_compressed(str(root/name), color=color, depth=np.round(z*1000).astype(np.uint16))
            frames.append({'file': name})
        (root/'metadata.json').write_text(json.dumps({'intrinsics': k.tolist(),
            'width': width, 'height': height, 'depth_scale': 1000, 'frames': frames}))
        jetscan.reconstruct(argparse.Namespace(input=str(root), voxel=0.01, min_depth=0.4, max_depth=2.5))
        cloud = o3d.io.read_point_cloud(str(root/'cloud.ply'))
        mesh = o3d.io.read_triangle_mesh(str(root/'mesh.ply'))
        assert len(cloud.points) > 100 and len(mesh.triangles) > 100
        points = np.asarray(cloud.points)
        assert 0.9 < np.median(points[:, 2]) < 1.1, 'Depth scale or extrinsic error'
        poses = json.loads((root/'trajectory.json').read_text())
        estimated = np.array(poses[-1]['camera_to_world'])
        assert abs(estimated[0, 3] - 0.016) < 0.01, 'Incorrect moving-camera pose'
        assert abs(estimated[1, 3]) < 0.01 and abs(estimated[2, 3]) < 0.01
        print('Synthetic moving-camera fusion, metric depth and export read-back PASSED')


if __name__ == '__main__':
    main()
