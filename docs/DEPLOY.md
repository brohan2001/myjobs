# Deployment (₹0, D29)

Everything runs on the user's old laptop: Ubuntu 26.04, x86_64, 16 GB RAM and 450 GB of disk, on the home Wi-Fi as
`rohan-laptop` (192.168.29.132). The laptop replaced the Oracle Always Free plan (D24).

## What runs where
| Piece | How | Reachable at |
|---|---|---|
| Postgres 16 and Redis 7 | `docker compose` (`restart: unless-stopped`) | 127.0.0.1 only |
| API (`myjobs serve --port 8090`) | systemd user unit `myjobs-api` | 127.0.0.1:8090 only |
| Crawler (`myjobs worker`) | systemd user unit `myjobs-worker` (MemoryMax 10G) | — |
| Web feed (`next start`) | systemd user unit `myjobs-web` | `http://rohan-laptop.local:3000`, home network only |
| Backups | `myjobs-backup.timer`: daily 03:30 `pg_dump -Fc` to `~/backups`, keeping 7 | — |

The user units are in `deploy/laptop/systemd/` and symlinked into `~/.config/systemd/user/`. Linger starts them at boot,
without anyone logging in.

## Fresh install
```bash
# on the Mac: send the code to the laptop (no GitHub needed)
git remote add laptop ssh://rohan@192.168.29.132/~/myjobs   # the repo there has receive.denyCurrentBranch=updateInstead
git push laptop revamp/phase-1-feed

# on the laptop
sudo ~/myjobs/deploy/laptop/root-setup.sh   # once: Docker, Node, Chromium libraries, no sleep, linger, ufw
~/myjobs/deploy/laptop/setup.sh             # venv, DBs, migrations, web build, services (add --restore DUMP to load data)
```

## Day to day
- **Ship a change:** `git push laptop <branch>` from the Mac, then on the laptop `deploy/laptop/setup.sh`, which rebuilds and
  restarts everything.
- **Logs:** `journalctl --user -u myjobs-worker -f` (likewise for `myjobs-api` and `myjobs-web`).
- **Status:** `systemctl --user status 'myjobs-*'`, `.venv/bin/myjobs health`, `.venv/bin/myjobs stats`.
- **Restore a backup:** stop the worker, drop and recreate the database, then run `setup.sh --restore ~/backups/<file>.dump`.

## Still open
- **Public access:** a free Cloudflare Tunnel. A stable hostname needs a domain on Cloudflare; a Quick Tunnel's URL changes on
  every restart. An alternative is DuckDNS plus a router port-forward (JioFiber is often behind CGNAT, so check this first).
- **Off-machine backups:** today's dumps sit on the same disk as the database.
- **Alerting:** a Healthchecks.io free ping driven by `myjobs health`.

## Fallback: Oracle Cloud Always Free (D24)
One A1 VM (4 OCPU, 24 GB RAM) in Mumbai or Hyderabad would run the same stack. The scripts assume Ubuntu, so they mostly carry
over. Sign-up needs a card, never upgrade to Pay-As-You-Go, and "out of capacity" errors in Indian regions are common.
