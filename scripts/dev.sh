#!/usr/bin/env bash
# Start the whole app locally with one command: Postgres + Redis (Docker), the crawler, the API and the web feed.
# Ctrl-C stops the crawler, API and web; Postgres and Redis keep running.
#
#   ./scripts/dev.sh               everything
#   ./scripts/dev.sh --no-worker   API + web only (browse existing jobs, no crawling)
#   ./scripts/dev.sh --no-browser  crawler skips boards that need Playwright
#
# Written for macOS's bash 3.2: no associative arrays, no `wait -n`.
set -euo pipefail

API_PORT=8090
WEB_PORT=3000
RUN_WORKER=1
WORKER_ARGS=""

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; }

for arg in "$@"; do
  case "$arg" in
    --no-worker) RUN_WORKER=0 ;;
    --no-browser) WORKER_ARGS="--no-browser" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }

# Wait up to $1 seconds for the command in the remaining arguments to succeed.
wait_for() {
  local timeout=$1; shift
  local i=0
  until "$@" >/dev/null 2>&1; do
    i=$((i + 1))
    [ "$i" -ge "$timeout" ] && return 1
    sleep 1
  done
}

# 1. Docker
if ! docker info >/dev/null 2>&1; then
  say "Starting Docker Desktop"
  open -a Docker || die "couldn't open Docker Desktop; is it installed?"
  wait_for 90 docker info || die "Docker didn't start within 90 seconds"
fi

# 2. Postgres + Redis
say "Starting Postgres and Redis"
docker compose up -d
wait_for 60 docker compose exec -T postgres pg_isready -U crawler || die "Postgres isn't accepting connections"
wait_for 30 docker compose exec -T redis redis-cli ping || die "Redis isn't responding"

# 3. Schema (no-op when current)
say "Applying database migrations"
alembic upgrade head

# 4. Refuse to start duplicates
for port in "$API_PORT" "$WEB_PORT"; do
  holder=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1 || true)
  if [ -n "$holder" ]; then
    die "port $port is already in use by PID $holder ($(ps -p "$holder" -o command= | sed -E "s|^[^ ]*/||" | cut -c1-100)).
Stop it with: kill $holder"
  fi
done
if [ "$RUN_WORKER" = 1 ] && pgrep -f "bin/myjobs worker" >/dev/null; then
  die "a crawler is already running (PID $(pgrep -f 'bin/myjobs worker' | head -1)). Stop it, or use --no-worker."
fi

if [ ! -d web/node_modules ]; then
  say "Installing web dependencies"
  (cd web && npm ci)
fi

# 5. Start the services, each in its own process group so Ctrl-C cleanup can stop the whole tree.
set -m
PGIDS=""
NAMES=""

# Prefix each output line with a coloured tag so three services can share one terminal.
start() {
  local name=$1 color=$2; shift 2
  ( "$@" 2>&1 | while IFS= read -r line; do printf '\033[%sm[%s]\033[0m %s\n' "$color" "$name" "$line"; done ) &
  PGIDS="$PGIDS $!"
  NAMES="$NAMES $name"
}

stopped=0
cleanup() {
  [ "$stopped" = 1 ] && return
  stopped=1
  echo
  say "Stopping crawler, API and web"
  for pgid in $PGIDS; do kill -TERM -- "-$pgid" 2>/dev/null || true; done
  # The worker drains in-flight work for up to 30 s before exiting.
  for pgid in $PGIDS; do wait "$pgid" 2>/dev/null || true; done
  say "Stopped. Postgres and Redis are still running; 'docker compose stop' shuts them down."
}
trap cleanup EXIT
trap 'exit 130' INT TERM

web_dev() { cd web && API_ORIGIN="http://127.0.0.1:$API_PORT" exec npm run dev -- --port "$WEB_PORT"; }

export PYTHONUNBUFFERED=1
[ "$RUN_WORKER" = 1 ] && start worker 33 myjobs worker $WORKER_ARGS
start api 36 myjobs serve --port "$API_PORT"
start web 35 web_dev

# 6. Open the feed once it answers
if wait_for 120 curl -sf "http://127.0.0.1:$WEB_PORT" -o /dev/null; then
  say "Feed:     http://localhost:$WEB_PORT"
  say "API docs: http://127.0.0.1:$API_PORT/api/docs"
  say "Press Ctrl-C to stop."
  open "http://localhost:$WEB_PORT"
else
  echo "The web app didn't answer within 120 seconds; check the [web] lines above." >&2
fi

# 7. Keep running until Ctrl-C, or until one service dies (then stop the rest so nothing runs half-broken).
while true; do
  set -- $NAMES
  for pgid in $PGIDS; do
    if ! kill -0 "$pgid" 2>/dev/null; then
      die "$1 exited; stopping the others. Its last lines are above."
    fi
    shift
  done
  sleep 2
done
