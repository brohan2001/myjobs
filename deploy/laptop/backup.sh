#!/usr/bin/env bash
# Nightly Postgres dump to ~/backups, keeping the last 7 (run by myjobs-backup.timer).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p ~/backups
out=~/backups/myjobs-$(date +%F).dump
docker compose exec -T postgres pg_dump -U crawler -Fc crawler > "$out.tmp"
mv "$out.tmp" "$out"
ls -1t ~/backups/myjobs-*.dump | tail -n +8 | xargs -r rm --
