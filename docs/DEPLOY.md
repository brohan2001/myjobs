# Deployment (D29)

Everything runs on the user's old laptop: Ubuntu 26.04, x86_64, 16 GB RAM, 450 GB disk. It sits on the home Wi-Fi as
`rohan-laptop` (192.168.29.132), and the Mac reaches it with `ssh rohan@192.168.29.132` (key login).

| Piece | How | Reachable at |
|---|---|---|
| Postgres 16, Redis 7 | `docker compose`, `restart: unless-stopped` | 127.0.0.1 only |
| API (`myjobs serve --port 8090`) | user unit `myjobs-api` | 127.0.0.1:8090 only |
| Crawler (`myjobs worker`) | user unit `myjobs-worker` | — |
| Web feed + `/admin` (`next start`) | user unit `myjobs-web` | `http://rohan-laptop.local:3000`, public via Cloudflare Tunnel (D32) |
| Public URL (`cloudflared`) | user unit `myjobs-tunnel`, token `TUNNEL_TOKEN` in `.env` | the tunnel's hostname (D32) |
| Backups | `myjobs-backup.timer`: daily 03:30 `pg_dump -Fc` to `~/backups`, keeps 7 | — |

The units are in `deploy/laptop/systemd/`, symlinked into `~/.config/systemd/user/`. Linger starts them at boot without a login.
The laptop never sleeps: the lid is ignored and the sleep targets are masked.

**Resource budget (D30):**
- api, web and worker run in `myjobs.slice` (300% CPU, 5 GB). Postgres and Redis get 1 CPU and ~1.25 GB in
  `docker-compose.yml`.
- Check the live limits with `systemctl --user show myjobs.slice -p CPUQuotaPerSecUSec,MemoryMax,MemoryCurrent` and
  `docker stats`.
- To change the budget, edit the slice and run `systemctl --user daemon-reload`. The services keep running.

## Ship a change
```bash
git push laptop <branch>                                  # from the Mac; remote = ssh://rohan@192.168.29.132/~/myjobs
ssh rohan@192.168.29.132 '~/myjobs/deploy/laptop/setup.sh' # reinstall, migrate, rebuild web, restart services
```
`updateInstead` only updates the branch that is checked out on the laptop. For a new branch, first run
`git -C ~/myjobs checkout <branch>` there.

## Fresh install
```bash
git init ~/myjobs && git -C ~/myjobs config receive.denyCurrentBranch updateInstead   # on the laptop, then push from the Mac
sudo ~/myjobs/deploy/laptop/root-setup.sh   # once: Docker, Node, Chromium libs + Chrome, no sleep, linger, ufw
~/myjobs/deploy/laptop/setup.sh             # add --restore <pg_dump file> to load existing data
```

## Operate
- **Admin:** `/admin` on the feed URL, logging in as user `admin` with `ADMIN_TOKEN` from `~/myjobs/.env` (D31). It shows
  when each board was crawled, errors by cause and health alerts, with recrawl, enable and disable buttons. It also shows
  CPU, memory, temperature and GPU use against the budget.
- **Public URL:** a tunnel made in the Cloudflare dashboard (Networks → Tunnels), with its public hostname pointed at
  `http://localhost:3000`. Its token goes in `.env` as `TUNNEL_TOKEN`; `setup.sh` installs `cloudflared` to
  `~/.local/bin` and runs `myjobs-tunnel`. Check it with `systemctl --user status myjobs-tunnel`.
- Logs: `journalctl --user -u myjobs-worker -f` (likewise `myjobs-api`, `myjobs-web`).
- Status: `systemctl --user status 'myjobs-*'`; `.venv/bin/myjobs health`; `.venv/bin/myjobs stats`.
- sudo asks for a password, so root steps can't run over a non-interactive SSH session.

## Not done yet
Off-machine backups, and alerting on `myjobs health`.
