# Compatibility changes and evidence

Recorded 2026-10-25 (America/Los_Angeles). This branch contains the latest code
verified through installation, synthetic reconstruction, and stationary hardware fusion/export smoke tests. Real moving-camera accuracy is not yet measured.

## Confirmed target

| Item | Observed value |
| --- | --- |
| Board / architecture | Jetson Nano, aarch64 |
| Operating system | Ubuntu 18.04.6 LTS |
| Jetson Linux | L4T R32.7.1, kernel 4.9.253-tegra |
| Python | 3.6.9 |
| RAM | 3.9 GiB total |
| Initial swap | About 1.9 GiB across four zram devices |
| Disk | About 100 GiB available before build |
| Camera | OAK device discovered by DepthAI, vendor 03e7 |

## 1. Keep packages compatible with stock Nano

DepthAI is pinned to 2.24.0.0, which has a Python 3.6 ARM64 wheel. NumPy is pinned
to 1.19.5; pip 21.3.1, setuptools 59.6.0 and wheel 0.37.1 retain Python 3.6 support.
CMake 3.22.6 provides the >=3.18 build interface needed by Open3D 0.13.0.
Ubuntu's OpenCV is exposed through a system-site-packages virtual environment.
Open3D is built from release tag v0.13.0 with CPU/OpenBLAS, GUI/CUDA/ML disabled,
and one compiler process to limit peak memory. JetPack and system Python are intact.

Files: setup.sh. Installation has reached Open3D Python-binding compilation.

## 2. Provide disk swap for the build

Observed failure: setup's 4 GB combined available RAM + free swap check failed
with approximately 1.5 GB available RAM and 1.9 GB free zram.

Change: add-swap.sh creates /var/tmp/jetscan-build.swap, allocates 4 GiB, sets mode
0600, initializes it and enables it. Existing zram remains enabled. The extra swap
is temporary and does not persist after reboot. The helper refuses an existing
inactive file and skips creation if the named swap is already active.

Correction during deployment: this Nano rejected dd's oflag=excl option. The helper
now exclusively creates the output using Bash noclobber redirection, with dd writing
to the already-open output descriptor. Actual blocks are written to avoid sparse
swap files on the older kernel.

Evidence: free and /proc/swaps confirm about 5.9 GiB total swap after activation.

## 3. Fix older OpenBLAS enum naming

Observed first compiler error: CBLAS_LAYOUT was not declared in BlasWrapper.h.
The installed /usr/include/aarch64-linux-gnu/cblas.h defines CBLAS_ORDER instead.
This caused gemm_cpu declarations to fail, followed by cascading MatmulCPU.cpp
errors and comma-operator diagnostics. It was not an out-of-memory failure.

Change: fix-openblas.py replaces exactly three `CBLAS_LAYOUT layout` declarations
with `decltype(CblasRowMajor) layout`, deriving the correct enum type from the
installed CBLAS header. It checks the expected number of occurrences and is safe
to rerun. The original header is saved alongside the patched file as
BlasWrapper.h.before-jetscan-blas-fix. setup.sh invokes this patch automatically.
No warning checks were disabled; matrix operations and data types remain intact.

Evidence: MatmulCPU.cpp compiled successfully, as did the following linear-algebra
sources. Full build subsequently reached 90% in the Python bindings.

## 4. Fix NumPy illegal instruction on Nano

Observed failure: importing NumPy 1.19.5 alone crashed with Illegal instruction,
before camera access or OpenCV import.

Change: set OPENBLAS_CORETYPE=ARMV8 before NumPy import, and limit its threads to 2.
The setting is applied to aarch64 inside jetscan.py and exported by setup.sh,
validate.sh and finish-setup.sh. Tests and selftest import jetscan before NumPy.
For ad-hoc Python commands use `export OPENBLAS_CORETYPE=ARMV8` first.

Evidence: NumPy 1.19.5 and OpenCV 3.2.0 imported successfully; all three geometry
unit tests passed on the Nano; three synchronized real RGB-D pairs were captured.

## 5. RGB-D odometry API and color handling

Runtime validation established that Open3D 0.13 uses max_depth_diff, min_depth
and max_depth. An earlier edit using newer API spellings caused AttributeError;
jetscan.py now uses names confirmed on the installed 0.13 object.
Odometry uses an intensity RGB-D image, while TSDF integration keeps
a separate RGB image for colored surfaces. Pose composition inverts the estimated
previous-to-current camera transform. Unit tests verify this direction with rotation.

Evidence: geometry tests and the five-frame synthetic motion/TSDF/export test now pass on the Nano.

## Current verification boundary

Passed: OS/architecture inspection, DepthAI discovery, NumPy/OpenCV imports,
three geometry tests, three real synchronized frame captures. An alignment preview
was retrieved, but the mostly ceiling scene is insufficient to establish calibration
or dimensional accuracy for useful foreground objects.

Completed: Open3D installation, five-frame synthetic motion/TSDF test, and ten-frame
hardware fusion/export read-back. Synthetic output: 15,281 points, 29,924 triangles.
Hardware output: 119,876 points, 206,701 triangles. logs/finish.exit is 0, and
logs/software-checks-passed exists. Final log: logs/finish-validation.log; hardware
log: logs/validation.log. Model directory: scans/check-20261025-110229.
Remaining: visual alignment in a suitable foreground scene, a real moving-camera
scan, and comparison with a known physical measurement. Script success does not
establish dimensional accuracy or drift behavior.

Remote deployment: /home/jw/jetscan-oak-20261024-230914.
Logs: build-resume.log (ongoing compilation), finish.log (installation and tests),
validation.log (real camera fusion/export), installed-versions.txt (package snapshot).

## Separate Windows profile issue

The user terminal reported a missing Conda executable in its PowerShell profile.
Running the deployment command with -NoProfile bypasses that unrelated startup
error. The user's profile was not edited.

## 6. Scope dependency checks to the scanner

Open3D compilation and wheel installation completed successfully. The broad
`pip check` then stopped on two pre-existing packages inherited through the
system-site-packages environment: launchpadlib lacked testresources, and NVIDIA
UFF required a newer protobuf than the system's 3.0.0. Neither package is used by
the scanner. Rather than modify JetPack's packages, setup and finish helpers now
save the full check in logs/system-package-check.log and run check-dependencies.py.
That checker resolves the pinned scanner requirements and imports NumPy, OpenCV,
DepthAI and Open3D; a scanner dependency or import failure still stops validation.
The first continuation attempt is in logs/finish.log; retry results are in
logs/finish-retry.log. This change does not claim the broader JetPack environment
has no dependency conflicts.

Final odometry validation is recorded in logs/finish-validation.log.

## Browser GUI (2026-10-25)

Added a Python 3.6 standard-library LAN server, live RGB/depth MJPEG streams,
capture start/stop with per-frame metadata checkpoints, recorded-frame replay,
offline reconstruction jobs, and a locally served Three.js r128 PLY viewer.
The camera pipeline is shared with CLI capture; calibration, dimensions, units
and timestamp pairing remain the same. One camera owner is shared among browsers;
reconstruction closes the camera and excludes concurrent captures.

Eight tests passed both locally and on the Nano, and the synthetic fusion test
still passes after factoring the camera generator. Browser testing recorded and
stopped 29 real frame pairs, replayed them, reconstructed all 29, and rendered the
155,713-point / 258,157-triangle result in mesh and point-cloud modes. Orbit was
tested interactively. These are stationary-scene checks, not a claim of measured
moving-camera accuracy.

Boot startup uses the existing active cron daemon and a marked user @reboot entry.
Existing cron entries are preserved, and flock prevents duplicate boot/manual
server processes. This avoids an administrator-password requirement; the optional
install-web.sh provides a systemd alternative. Boot configuration was inspected;
the Nano was not rebooted during this deployment. No new Python packages, no
changes to JetPack, and no changes to camera calibration were required.

## Native camera crash recovery (2026-10-25)

The web process stopped after DepthAI logged "Device crashed" and aborted Python
with SIGABRT. Port 8080 was no longer listening. The @reboot entry and cron were
still intact; the initial exec-only boot wrapper could not recover a process
that died between reboots. This was not an SSH or firewall failure.

start-web.sh now retains a small shell supervisor outside Python, holds the
single-instance lock and restarts the web process after five seconds. SIGTERM
to the supervisor forwards shutdown to its child and exits without restarting.
The server also closes preview after 60 seconds without browser status polls,
while preserving active recordings and reconstruction jobs.

Ten tests pass locally and on Nano. An idle-only recovery test deliberately
terminated the Python child; the same supervisor started a new child and the API
returned HTTP 200, with port 8080 bound on all interfaces. This verifies recovery
from an abrupt process exit; it does not establish the cause of the OAK device
crash or guarantee USB hardware reliability. Existing saved scans were preserved.
