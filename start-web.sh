#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p logs scans
# The same lock is used by boot and manual starts, so the camera has one owner.
exec 9>logs/web.lock
flock -n 9 || exit 0
printf '%s\n' "$$" > logs/web-supervisor.pid
export OPENBLAS_CORETYPE=ARMV8
export OPENBLAS_NUM_THREADS=2
export OMP_NUM_THREADS=2
export PYTHONUNBUFFERED=1
# Keep the supervisor outside Python: a native DepthAI abort can kill Python
# without running any Python exception handler or cleanup code.
stopping=0
child=
stop() {
    stopping=1
    if [[ -n "$child" ]]; then kill -TERM "$child" 2>/dev/null || true; fi
}
trap stop TERM INT
while (( stopping == 0 )); do
    .venv/bin/python webapp.py --host 0.0.0.0 --port 8080 &
    child=$!
    printf '%s\n' "$child" > logs/web.pid
    code=0
    wait "$child" || code=$?
    if (( stopping != 0 )); then
        wait "$child" 2>/dev/null || true
        break
    fi
    child=
    printf '%s webserver exited (%s); restarting in 5 seconds\n' "$(date -Is)" "$code"
    sleep 5 &
    wait $! || true
done
