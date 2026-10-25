#!/usr/bin/env bash
# Run on the Nano as its regular user. Never run with bash -x.
set -euo pipefail
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
cd "$(dirname "$0")"
mkdir -p logs
exec > >(tee -a logs/setup.log) 2>&1
echo '--- Hardware and OS inspection ---'
uname -a
cat /etc/os-release
cat /etc/nv_tegra_release 2>/dev/null || true
free -h
df -h .
command -v lsusb >/dev/null && lsusb || true
python3 --version
if [[ "$(uname -m)" != aarch64 ]]; then
    echo 'Expected aarch64 Jetson. No packages installed.'; exit 1
fi
. /etc/os-release
if [[ "$ID" != ubuntu || "$VERSION_ID" != 18.04 ]]; then
    echo 'This installer targets stock Nano JetPack 4 / Ubuntu 18.04.'
    echo 'Stop here and use the inspection log to choose a stack for this OS.'; exit 1
fi
python3 -c 'import sys; assert sys.version_info[:2] == (3,6), "Expected stock Python 3.6"'
available=$(df -Pk . | awk 'END {print $4}')
if (( available < 12582912 )); then
    echo 'At least 12 GiB free disk is required for the source build.'; exit 1
fi
memory=$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)
swap=$(awk '/SwapFree:/ {print $2}' /proc/meminfo)
if (( memory + swap < 4000000 )); then
    echo 'Need at least 4 GB combined available RAM and swap; see README.'; exit 1
fi
# sudo prompts on the controlling terminal; credentials are never piped or saved.
sudo -v
sudo apt-get update
sudo apt-get install -y build-essential git curl ca-certificates pkg-config \
    python3-dev python3-venv python3-numpy python3-opencv python3-pip \
    libusb-1.0-0-dev libudev-dev libopenblas-dev liblapack-dev liblapacke-dev gfortran \
    libgl1-mesa-dev libglu1-mesa-dev libglew-dev libglfw3-dev \
    libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
    libjpeg-dev libpng-dev libssl-dev usbutils
if [[ ! -d .venv ]]; then python3 -m venv --system-site-packages .venv; fi
source .venv/bin/activate
python -m pip install 'pip==21.3.1' 'setuptools==59.6.0' 'wheel==0.37.1'
python -m pip install 'cmake==3.22.6' 'numpy==1.19.5'
python -m pip install --only-binary=:all: 'depthai==2.24.0.0'
printf '%s\n' 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0660", GROUP="plugdev", TAG+="uaccess"' \
    | sudo tee /etc/udev/rules.d/80-jetscan-oak.rules >/dev/null
sudo usermod -a -G plugdev "$USER"
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb
mkdir -p vendor
if [[ ! -d vendor/Open3D ]]; then
    git clone --recursive --branch v0.13.0 --depth 1 https://github.com/isl-org/Open3D.git vendor/Open3D
fi
git -C vendor/Open3D describe --tags --exact-match | grep -Fx v0.13.0
python fix-openblas.py
if ! python -c 'import open3d; assert open3d.__version__.startswith("0.13.0")' 2>/dev/null; then
    cmake -S vendor/Open3D -B vendor/Open3D/build \
        -DCMAKE_BUILD_TYPE=Release -DPYTHON_EXECUTABLE="$VIRTUAL_ENV/bin/python" \
        -DBUILD_PYTHON_MODULE=ON -DBUILD_CUDA_MODULE=OFF -DBUILD_GUI=OFF \
        -DBUILD_WEBRTC=OFF -DBUILD_JUPYTER_EXTENSION=OFF -DBUILD_RPC_INTERFACE=OFF \
        -DBUILD_EXAMPLES=OFF -DBUILD_UNIT_TESTS=OFF -DBUILD_BENCHMARKS=OFF \
        -DBUILD_LIBREALSENSE=OFF -DBUILD_AZURE_KINECT=OFF \
        -DBUILD_TENSORFLOW_OPS=OFF -DBUILD_PYTORCH_OPS=OFF -DBUNDLE_OPEN3D_ML=OFF \
        -DWITH_FAISS=OFF -DWITH_IPPICV=OFF -DUSE_BLAS=ON
    cmake --build vendor/Open3D/build --parallel 1
    cmake --build vendor/Open3D/build --target install-pip-package --parallel 1
fi
python -m pip check > logs/system-package-check.log 2>&1 || true
python check-dependencies.py
python -m pip freeze > logs/installed-versions.txt
python -m unittest discover -s tests -v
python selftest.py
touch logs/software-checks-passed
echo 'Software checks passed. Log in again to refresh plugdev membership, then run validate.sh.'
