# JetScan OAK-D Lite

A headless RGB-D scanner using an OAK-D Lite for RGB capture, stereo depth and
alignment, and a Jetson Nano for offline RGB-D odometry and colored TSDF fusion.
It exports colored point clouds and meshes in metres.

**Tested on 2026-10-25:** installation, synthetic moving-camera reconstruction,
and a ten-frame stationary camera capture/fusion/export test passed. The real
capture produced 119,876 points and 206,701 triangles, with successful PLY
read-back. Real moving-camera accuracy and physical scale still need measurement.

## Requirements

- Jetson Nano running **Ubuntu 18.04 / JetPack 4**, aarch64, Python 3.6.
  The tested board has 4 GB RAM, L4T R32.7.1 and Python 3.6.9.
- OAK-D Lite connected to a Nano USB3 port with a data-capable USB cable.
- Adequate Nano power and cooling, internet access for installation, and at least
  **12 GiB free disk space after adding swap**.
- At least 4 GB combined available RAM and free swap for the build. The tested
  setup needed an additional 4 GiB disk swap, described below.
- SSH access if operating remotely. Examples use `jw@10.0.0.4`; replace this
  account/address with your own when using a different Nano.

See [HARDWARE.md](HARDWARE.md) for connections and hardware changes. The original RealSense enclosure, electronics and CUDA setup pages remain in
the [reference project](https://github.com/devshank3/JetScan); they are not included
in this standalone repository.

## Run the system already installed on this Nano

The tested installation is `/home/jw/jetscan-oak-20261024-230914`. Open PowerShell
on your PC and connect:

```powershell
ssh jw@10.0.0.4
```

Then run these commands **on the Nano**:

```bash
cd ~/jetscan-oak-20261024-230914
source .venv/bin/activate
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=2
python jetscan.py doctor
mkdir -p scans
SCAN="scans/scan-$(date +%Y%m%d-%H%M%S)"
python jetscan.py capture "$SCAN" --frames 150
python jetscan.py reconstruct "$SCAN" --voxel 0.01 --min-depth 0.4 --max-depth 2.5
echo "Scan saved to $PWD/$SCAN"
```

Start with the camera stationary, aimed at textured matte objects in diffuse
light, about 0.5-2 metres away. For a moving scan, move the camera very slowly and
keep substantial overlap. The scene must remain stationary: do not rotate an
object on a turntable. Begin with short scans; real moving-camera tracking has
not yet been validated on this setup.

Capture stops after the requested frame count. Ctrl+C preserves the metadata for
frames already saved; at least two saved frames are needed for reconstruction.
Reconstruction can be rerun from the saved dataset. Each capture requires a new
output directory; the timestamp above provides one.

## Install on a Nano from scratch

### 1. Connect and obtain the source

From your PC:

```powershell
ssh jw@10.0.0.4
```

Run the following **on the Nano**, as its regular user:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone --branch master https://github.com/JiaweiChenKodomo/JetScan-OAK-D-Lite.git
cd JetScan-OAK-D-Lite
```

Enter passwords only at the terminal's SSH/sudo prompts. No password should be
added to source files, commands, or logs.

### 2. Add build swap if needed

Inspect memory and disk:

```bash
free -h
df -h .
cat /proc/swaps
```

On the tested 4 GB Nano, the existing zram swap was insufficient. This helper
adds **4 GiB temporary disk swap**, leaving existing zram enabled:

```bash
sudo bash add-swap.sh
```

It needs at least 6 GiB free space before creation, refuses to overwrite an
existing inactive swap file, and skips creation if its swap is already active.
The extra swap does not survive a reboot. If you reboot before finishing the
build, re-enable the file you created, then resume setup:

```bash
sudo swapon /var/tmp/jetscan-build.swap
```

Run that command only when the file exists and is not already active. Do not
rerun `mkswap` on an active swap file. Keep at least 12 GiB free for the source
build after allocating swap.

### 3. Install dependencies and build Open3D

From the `JetScan` directory on the Nano:

```bash
bash setup.sh
```

This installs apt build dependencies, creates `.venv`, installs pinned Python
packages, configures OAK USB permissions and builds Open3D with one compiler
process. It applies the required OpenBLAS/ARM compatibility fixes automatically,
then runs dependency, geometry and synthetic reconstruction checks. **The build
can take hours.** Keep the Nano powered and cooled; keep the terminal connected.

The supported stack is DepthAI 2.24.0.0, NumPy 1.19.5, Ubuntu OpenCV and an
ARM64 CPU build of Open3D 0.13.0. CUDA, GUI and ML extensions are disabled.
The installer stops for an unsupported OS/architecture/Python combination.
It does not replace JetPack, system Python or CUDA.

If installation is interrupted, reconnect, enter the same directory and run
`bash setup.sh` again. It reuses the existing build; do not clone or deploy again.
Logs are saved in `logs/setup.log`.

### 4. Refresh USB permissions and validate

Log out and reconnect so your new `plugdev` group membership takes effect:

```bash
exit
```

From the PC:

```powershell
ssh jw@10.0.0.4
```

On the Nano, aim the camera at a stationary textured scene and run:

```bash
cd ~/JetScan-OAK-D-Lite
bash validate.sh
```

Validation checks camera discovery/calibration, captures ten RGB-depth pairs,
fuses them, exports models and reads the PLY files back. Success ends with
`Camera/capture/fusion/export smoke test passed` and a scan directory path.
The log is `logs/validation.log`. Inspect that scan's `alignment.png` before
trusting an object scan; green depth edges should follow visible boundaries,
with expected differences at occlusions.

For normal use, follow the run commands above, replacing the installation path
with `~/JetScan-OAK-D-Lite`.

## Optional: deploy automatically from Windows

This alternative uses the SSH key already installed for `jw@10.0.0.4`. The target
is set at the top of `deploy.ps1`; edit it when deploying to a different Nano.
Windows needs Git, OpenSSH (`ssh`/`scp`) and `tar` available in PowerShell.

```powershell
git clone --branch master https://github.com/JiaweiChenKodomo/JetScan-OAK-D-Lite.git
cd JetScan-OAK-D-Lite
ssh -o BatchMode=yes jw@10.0.0.4 "whoami"
scp .\add-swap.sh jw@10.0.0.4:jetscan-add-swap.sh
ssh -t jw@10.0.0.4 "sudo bash ~/jetscan-add-swap.sh"
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy.ps1 -Validate
```

The swap step is needed only if memory plus free swap is insufficient. Sudo
prompts securely in the terminal. `-NoProfile` bypasses unrelated PowerShell
profile errors; the execution-policy setting applies to that process.

The deploy helper creates a timestamped Nano directory such as
`~/jetscan-oak-20261025-120000`, preserving existing deployments and scans.
Use the actual printed directory for subsequent commands. To resume a failed
installation without creating another deployment:

```powershell
ssh -t jw@10.0.0.4 'cd ~/YOUR_DEPLOYMENT_DIRECTORY && bash setup.sh'
ssh -t jw@10.0.0.4 'cd ~/YOUR_DEPLOYMENT_DIRECTORY && bash validate.sh'
```

## Script commands and output files

Run commands in the Nano installation directory with `.venv` activated.

| Command | Purpose |
| --- | --- |
| `python jetscan.py doctor` | Check camera discovery, USB speed, sockets and calibration |
| `python jetscan.py capture scans/example --frames 150` | Save synchronized RGB-depth frames into a new directory |
| `python jetscan.py reconstruct scans/example` | Estimate camera poses, fuse depth and export models |
| `python selftest.py` | Test synthetic moving-camera fusion and metric export |
| `bash validate.sh` | Run the stationary real-camera smoke test |

Reconstruction options: `--voxel 0.01` uses 1 cm voxels; `--min-depth 0.4` and
`--max-depth 2.5` retain depths from 0.4 to 2.5 metres. Increase `--voxel` to `0.02`
for lower memory use and coarser output. Failed tracking stops reconstruction;
it does not relocalize or fuse an uncertain pose.

| File in the scan directory | Contents |
| --- | --- |
| `000000.npz`, etc. | Paired RGB uint8 and depth uint16 frames |
| `metadata.json` | Calibration, frame timestamps and valid-depth fractions |
| `alignment.png` | First frame with green depth edges over RGB |
| `cloud.ply` | Colored fused point cloud |
| `mesh.ply` | Surface mesh with vertex colors |
| `mesh.obj` | Geometry interchange mesh; no texture atlas |
| `trajectory.json` | Camera-to-world pose for each integrated frame |

Coordinates are metres, relative to the initial camera: X right, Y down, Z
forward. PLY is the preferred color interchange format. Meshes are not guaranteed
watertight. RGB is rectified; depth is aligned to RGB at 640x360, and saved pairs
must have timestamps within 20 ms.

## Copy a scan to your PC

Open a **second PowerShell terminal on the PC**, not inside the SSH session.
For a direct Nano installation, replace `SCAN_DIRECTORY` with the scan name:

```powershell
scp -r jw@10.0.0.4:JetScan-OAK-D-Lite/scans/SCAN_DIRECTORY .\downloaded-scan
```

For the existing tested deployment, use
`jetscan-oak-20261024-230914/scans/SCAN_DIRECTORY` as the remote path instead.
Open `cloud.ply` or `mesh.ply` in a 3D viewer such as CloudCompare or MeshLab.
Compare a known physical dimension with the reconstructed measurement before
using the scan for dimensional work.

## Troubleshooting and limitations

- **No OAK device:** check the cable, power and USB3 connection; reconnect the
  camera and close other DepthAI processes. Log out/in after installing USB rules.
- **Insufficient memory:** run `free -h`, enable the build swap and close unused
  applications. Resume `bash setup.sh` in the same directory.
- **NumPy illegal instruction:** export `OPENBLAS_CORETYPE=ARMV8` before ad-hoc
  Python commands. The scanner and setup/validation scripts already apply it.
- **Inherited system package conflicts:** the broad report is in
  `logs/system-package-check.log`. `check-dependencies.py` validates the scanner's
  own pinned requirements; unrelated JetPack package conflicts are not repaired.
- **Tracking lost:** use shorter captures, slower camera motion and more texture.
  Avoid glass, mirrors and featureless surfaces; keep the scene stationary.
- **OBJ triangle-normal warning:** PLY output and read-back were verified; the
  OBJ exporter does not include triangle normals.

This implementation uses sequential odometry and TSDF fusion. It does not include
the original project's full submap registration, loop closure, global optimization
or GPU performance. Capture compression can reduce effective frame rate; large
scans have no hard volume-memory bound. A stationary smoke test and synthetic
motion test do not establish real moving-camera accuracy.

Detailed changes and evidence: [COMPATIBILITY.md](COMPATIBILITY.md) and
[VERIFICATION.txt](VERIFICATION.txt).

## References

- [Original JetScan forum project](https://forums.developer.nvidia.com/t/jetscan-portable-and-instant-rgb-d-3d-scanner/116476)
- [Original JetScan repository](https://github.com/devshank3/JetScan)
- [DepthAI pinned release](https://pypi.org/project/depthai/2.24.0.0/)
- [Luxonis RGB-depth alignment example](https://github.com/luxonis/depthai-python/blob/v2.24.0.0/examples/StereoDepth/rgb_depth_aligned.py)
- [Open3D 0.13 build requirements](https://www.open3d.org/docs/0.13.0/compilation.html)

## Relationship to original JetScan

This is a standalone implementation inspired by the original
[JetScan project by devshank3](https://github.com/devshank3/JetScan).
The original RGB-D scanning concept is the reference; no original JetScan runtime
code, CAD, wiring drawings or scan assets are included or required. Our scanner
uses the DepthAI and Open3D libraries directly. The earlier adaptation work is
also available in [JiaweiChenKodomo/JetScan](https://github.com/JiaweiChenKodomo/JetScan).

The core implementation is unchanged from the Nano-validated adaptation. Source
history starts independently here; validation details are in VERIFICATION.txt.
See [LICENSE](LICENSE).
