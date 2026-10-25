#!/usr/bin/env bash
# Finish an already-started build without sudo or another password prompt.
set -euo pipefail
cd "$(dirname "$0")"
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=2
source .venv/bin/activate
mkdir -p logs
: > logs/finish.exit
trap 'code=$?; printf "%s\n" "$code" > logs/finish.exit; exit "$code"' EXIT
if [[ $# -gt 0 && "$1" =~ ^[0-9]+$ ]]; then
    echo "Waiting for existing build process $1"
    while kill -0 "$1" 2>/dev/null; do sleep 10; done
fi
python fix-openblas.py
if ! python -c 'import open3d; assert open3d.__version__.startswith("0.13.0")' 2>/dev/null; then
    cmake --build vendor/Open3D/build --parallel 1
    cmake --build vendor/Open3D/build --target install-pip-package --parallel 1
fi
python -m pip check > logs/system-package-check.log 2>&1 || true
python check-dependencies.py
python -m pip freeze > logs/installed-versions.txt
python -m unittest discover -s tests -v
python selftest.py
touch logs/software-checks-passed
bash validate.sh
printf '%s\n' 'Software and hardware smoke checks passed.'
