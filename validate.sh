#!/usr/bin/env bash
set -euo pipefail
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
cd "$(dirname "$0")"
source .venv/bin/activate
export OMP_NUM_THREADS=2
mkdir -p logs scans
exec > >(tee -a logs/validation.log) 2>&1
python jetscan.py doctor
scan="scans/check-$(date +%Y%m%d-%H%M%S)"
echo 'Keep the camera stationary, aimed at textured matte objects about 0.5 to 2 metres away.'
python jetscan.py capture "$scan" --frames 10
python jetscan.py reconstruct "$scan"
python - "$scan" <<'PY'
import sys
from pathlib import Path
import open3d as o3d
root = Path(sys.argv[1])
cloud = o3d.io.read_point_cloud(str(root / 'cloud.ply'))
mesh = o3d.io.read_triangle_mesh(str(root / 'mesh.ply'))
assert len(cloud.points) > 100, 'Too few exported points'
assert len(mesh.triangles) > 100, 'Too few exported triangles'
print('Export read-back passed:', len(cloud.points), 'points;', len(mesh.triangles), 'triangles')
PY
echo "Camera/capture/fusion/export smoke test passed: $scan"
echo 'Inspect alignment.png: green depth edges should coincide with visible object boundaries.'
echo 'This stationary test does not establish moving-camera accuracy or metric calibration.'
