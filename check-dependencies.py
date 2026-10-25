"""Validate scanner requirements without failing on unrelated inherited JetPack tools."""
import jetscan  # Establish ARMv8 NumPy settings before importing compiled packages.
import pkg_resources
import cv2
import depthai
import open3d

pkg_resources.require([
    'depthai==2.24.0.0', 'numpy==1.19.5', 'open3d>=0.13.0,<0.14',
    'setuptools==59.6.0', 'wheel==0.37.1', 'cmake==3.22.6',
])
print('Scanner dependency requirements passed; OpenCV:', cv2.__version__,
      'DepthAI:', depthai.__version__, 'Open3D:', open3d.__version__)
