#!/usr/bin/env bash
# Install a user-owned boot entry without an administrator password.
set -euo pipefail
cd "$(dirname "$0")"
test -x .venv/bin/python
test -f web/vendor/three.min.js
command -v flock >/dev/null
command -v crontab >/dev/null
mkdir -p logs scans
python3 - "$PWD" <<'PY'
import subprocess
import sys
import shlex
from pathlib import Path
root = Path(sys.argv[1])
old = subprocess.run(['crontab', '-l'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
if old.returncode not in (0, 1) or (old.returncode == 1 and 'no crontab' not in old.stderr.lower()):
    raise SystemExit('Could not read current crontab: ' + old.stderr)
lines = []
inside = False
for line in old.stdout.splitlines():
    if line == '# BEGIN JETSCAN WEB':
        inside = True
    elif line == '# END JETSCAN WEB':
        inside = False
    elif not inside:
        lines.append(line)
command = '/bin/bash {} >> {} 2>&1'.format(shlex.quote(str(root / 'start-web.sh')),
                                           shlex.quote(str(root / 'logs/web.log')))
command = command.replace('%', r'\%')
lines += ['# BEGIN JETSCAN WEB', '@reboot ' + command, '# END JETSCAN WEB']
subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n', universal_newlines=True, check=True)
print('Installed JetScan @reboot entry; other cron entries preserved.')
PY
nohup bash ./start-web.sh >> logs/web.log 2>&1 < /dev/null &
echo 'Web interface starting on port 8080; log: logs/web.log'
