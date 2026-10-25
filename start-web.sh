#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs scans
# The same lock is used by boot and manual starts, so the camera has one owner.
exec 9>logs/web.lock
flock -n 9 || exit 0
printf '%s\n' "$$" > logs/web.pid
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=2
export PYTHONUNBUFFERED=1
exec .venv/bin/python webapp.py --host 0.0.0.0 --port 8080
