#!/usr/bin/env bash
# Install or update myjobs on the laptop, as your normal user (D29). Run deploy/laptop/root-setup.sh first, once.
# Safe to re-run after every `git pull` / push: it rebuilds and restarts the services.
#
#   deploy/laptop/setup.sh               install/update and restart everything
#   deploy/laptop/setup.sh --restore F   also load a pg_dump -Fc file F into an empty database first
set -euo pipefail

cd "$(dirname "$0")/../.."
repo=$(pwd)
say() { printf '\033[1m==> %s\033[0m\n' "$*"; }

restore=""
[ "${1:-}" = "--restore" ] && restore=${2:?--restore needs a dump file}

say "Python environment"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
[ -d .venv ] || uv venv --python 3.13 .venv
uv pip install -q -p .venv -e ".[dev]"
.venv/bin/python -m playwright install chromium
[ -f .env ] || { cp .env.example .env; chmod 600 .env; }

say "Postgres and Redis"
docker compose up -d
until docker compose exec -T postgres pg_isready -U crawler -q; do sleep 1; done
if [ -n "$restore" ]; then
  say "Restoring $restore"
  docker compose exec -T postgres pg_restore -U crawler -d crawler --no-owner -j 4 < "$restore"
fi
.venv/bin/alembic upgrade head
if [ -z "$restore" ] && [ "$(docker compose exec -T postgres psql -U crawler -tAc 'select count(*) from location')" = 0 ]; then
  .venv/bin/python scripts/load_geonames.py
  .venv/bin/python scripts/populate_taxonomy.py
fi

say "Web app"
(cd web && npm ci --no-audit --no-fund && npm run build)

say "Services"
mkdir -p ~/.config/systemd/user ~/backups
ln -sf "$repo"/deploy/laptop/systemd/* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now myjobs-api myjobs-worker myjobs-web myjobs-backup.timer
systemctl --user restart myjobs-api myjobs-worker myjobs-web

say "Feed: http://$(hostname).local:3000  (or http://$(hostname -I | awk '{print $1}'):3000)"
