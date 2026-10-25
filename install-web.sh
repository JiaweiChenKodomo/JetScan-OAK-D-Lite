#!/usr/bin/env bash
# Run with sudo from the scanner installation folder. No credential is saved.
set -euo pipefail
if (( EUID != 0 )); then echo 'Run: sudo bash install-web.sh'; exit 1; fi
app_dir=$(cd "$(dirname "$0")" && pwd)
app_user=${SUDO_USER:-}
if [[ -z "$app_user" || "$app_user" == root ]]; then
    echo 'Run sudo from the regular Nano account so the service runs as that user.'; exit 1
fi
if [[ "$app_dir" == *'%'* || "$app_dir" == *'"'* || "$app_dir" == *$'\n'* ]]; then
    echo 'Unsupported installation directory.'; exit 1
fi
test -x "$app_dir/.venv/bin/python"
test -f "$app_dir/webapp.py"
test -f "$app_dir/web/vendor/three.min.js"
mkdir -p "$app_dir/scans"
chown "$app_user:$(id -gn "$app_user")" "$app_dir/scans"
cat > /etc/systemd/system/jetscan-web.service <<EOF
[Unit]
Description=JetScan OAK-D Lite LAN interface
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$app_user
WorkingDirectory="$app_dir"
Environment=OPENBLAS_CORETYPE=ARMV8
Environment=OPENBLAS_NUM_THREADS=2
Environment=OMP_NUM_THREADS=2
Environment=PYTHONUNBUFFERED=1
ExecStart="$app_dir/.venv/bin/python" "$app_dir/webapp.py" --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=5
TimeoutStopSec=40
KillMode=control-group
NoNewPrivileges=true
UMask=0027

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now jetscan-web.service
systemctl --no-pager status jetscan-web.service
echo 'Open http://<Nano-LAN-IP>:8080 on a computer on the same LAN.'
