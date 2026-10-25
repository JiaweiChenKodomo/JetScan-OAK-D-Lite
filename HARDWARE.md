# Hardware: Jetson Nano with OAK-D Lite

This adaptation uses a Jetson Nano and a Luxonis OAK-D Lite in place of the
original JetScan RealSense camera. It runs headlessly over SSH.

## Tested setup

| Component | Role / observed configuration |
| --- | --- |
| NVIDIA Jetson Nano, 4 GB RAM | Capture host and CPU reconstruction |
| Luxonis OAK-D Lite | RGB camera, stereo depth computation and RGB-depth alignment |
| USB data connection | Camera connected at USB3 SUPER speed during validation |
| Nano storage | About 100 GiB free before building; installer requires 12 GiB free |
| Nano cooling and power supply | Keep the board cooled and adequately powered during the long build |
| Local Wi-Fi / SSH | Remote commands and file transfer using SSH keys |

Observed software: Ubuntu 18.04.6, L4T R32.7.1, aarch64, Python 3.6.9.
A separate display, keyboard and battery assembly are optional for this headless
workflow; the original display and battery electronics were not validated here.

## Connections and placement

1. Connect the OAK-D Lite USB port to a Nano USB3 host port with a data-capable
   cable. The camera is a USB device, not a CSI ribbon-camera connection.
2. Connect and power the Nano according to its board's requirements.
3. Confirm Wi-Fi/SSH access, then follow the root README for installation.
4. Run `python jetscan.py doctor` in the virtual environment. Check for all three
   camera sockets and USB SUPER speed. USB2 operation has not been validated here.
5. Keep both stereo lenses and the RGB lens unobstructed. Use a stationary,
   textured scene and move the camera slowly for a real scan.

The STL files and wiring drawings in the [original JetScan repository](https://github.com/devshank3/JetScan) describe its RealSense scanner; they are not included here. Their camera opening, mounting points and electronics
layout have not been adapted or verified for OAK-D Lite. A new enclosure design
is outside the implemented software adaptation.

## What changed from original JetScan

| Original design | This adaptation |
| --- | --- |
| Intel RealSense camera and librealsense | OAK-D Lite and DepthAI 2.24.0.0 |
| Historical Open3D CUDA fork | Open3D 0.13.0 CPU build for stock Nano OS |
| Original portable enclosure/electronics | USB-connected headless setup; original enclosure linked as an external reference |
| Fragment/submap reconstruction workflow | Sequential RGB-D odometry and TSDF fusion |
| Original timing/results | New scripted validation results in VERIFICATION.txt |

Stereo depth and alignment execute on the OAK; TSDF reconstruction executes on
the Nano CPU. This code does not implement the original full submap optimization,
loop closure, relocalization, or GPU performance claims.

## Validation performed

Installation, synthetic moving-camera fusion and stationary real-camera capture,
fusion and export checks passed. Ten real RGB-D pairs produced 119,876 points and
206,701 triangles, and PLY read-back passed. Real moving-camera tracking, physical
scale and dimensional accuracy still need measurement with a suitable scene.
See [COMPATIBILITY.md](COMPATIBILITY.md), [VERIFICATION.txt](VERIFICATION.txt), and
[README.md](README.md) for the exact software configuration and operation steps.
