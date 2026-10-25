#!/usr/bin/env bash
set -euo pipefail
if (( EUID != 0 )); then
    echo 'Run with sudo bash add-swap.sh in an interactive terminal.'; exit 1
fi
swapfile=/var/tmp/jetscan-build.swap
if awk -v target="$swapfile" 'NR>1 && $1==target {found=1} END {exit !found}' /proc/swaps; then
    echo 'JetScan build swap is already active.'
    free -h
    exit 0
fi
if [[ -e "$swapfile" || -L "$swapfile" ]]; then
    echo "Refusing to modify existing inactive file: $swapfile"
    echo 'Inspect it before proceeding.'; exit 1
fi
available=$(df -Pk /var/tmp | awk 'END {print $4}')
if (( available < 6291456 )); then
    echo 'Need at least 6 GiB free disk space before adding 4 GiB swap.'; exit 1
fi
umask 077
# Shell noclobber exclusively creates the output file; dd writes via its open descriptor.
# Allocating actual blocks avoids sparse-file rejection by older Jetson kernels.
( set -o noclobber; dd if=/dev/zero bs=1M count=4096 status=progress > "$swapfile" )
chmod 600 "$swapfile"
mkswap "$swapfile"
swapon "$swapfile"
free -h
cat /proc/swaps
echo 'Added 4 GiB temporary disk swap; existing zram is unchanged.'
echo 'This swap is not configured to persist after reboot.'
