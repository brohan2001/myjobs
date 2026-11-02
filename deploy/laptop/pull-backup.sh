#!/usr/bin/env bash
# Run on the Mac: copy the laptop's newest nightly dump to ~/myjobs-backups and keep the last 3 (off-machine copy).
# Daily via a LaunchAgent (docs/DEPLOY.md); a run just fails while the laptop is unreachable.
set -euo pipefail
host=${MYJOBS_HOST:-rohan@192.168.29.132}
dest=~/myjobs-backups
mkdir -p "$dest"
latest=$(ssh -o ConnectTimeout=10 "$host" 'ls -1t ~/backups/myjobs-*.dump | head -1')
rsync -t --partial "$host:$latest" "$dest/"
ls -1t "$dest"/myjobs-*.dump | tail -n +4 | xargs -r rm --
echo "pulled $(basename "$latest")"
