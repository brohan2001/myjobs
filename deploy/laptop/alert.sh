#!/usr/bin/env bash
# Push new `myjobs health` alerts to ntfy.sh (run by myjobs-alert.timer). Off unless NTFY_TOPIC is set in .env.
# Repeats are skipped: an alert is sent again only after the set of firing checks changes.
set -uo pipefail
cd "$(dirname "$0")/../.."
topic=$(sed -n 's/^NTFY_TOPIC=//p' .env)
[ -n "$topic" ] || exit 0
state=~/.cache/myjobs-alerts
out=$(.venv/bin/myjobs health 2>&1) && { rm -f "$state"; exit 0; }
key=$(grep -oE 'ALERT [a-z_]+(: [a-z_]+:)?' <<<"$out" || echo "health check crashed")
[ "$key" = "$(cat "$state" 2>/dev/null)" ] && exit 0
mkdir -p ~/.cache && printf '%s\n' "$key" > "$state"
curl -fsS -H "Title: myjobs health" -d "$(grep ALERT <<<"$out" || tail -5 <<<"$out")" "https://ntfy.sh/$topic" >/dev/null
