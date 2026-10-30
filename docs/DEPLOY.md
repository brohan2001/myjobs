# Deployment (D29)

Everything runs on the user's old laptop: Ubuntu 26.04, x86_64, 16 GB RAM, 450 GB disk. It sits on the home Wi-Fi as
`rohan-laptop` (192.168.29.132), and the Mac reaches it with `ssh rohan@192.168.29.132` (key login).

| Piece | How | Reachable at |
|---|---|---|
| Postgres 16, Redis 7 | `docker compose`, `restart: unless-stopped` | 127.0.0.1 only |
| API (`myjobs serve --port 8090`) | user unit `myjobs-api` | 127.0.0.1:8090 only |
| Crawler (`myjobs worker`) | user unit `myjobs-worker`, MemoryMax 10G | — |
| Web feed (`next start`) | user unit `myjobs-web` | `http://rohan-laptop.local:3000` (home network) |
| Backups | `myjobs-backup.timer`: daily 03:30 `pg_dump -Fc` to `~/backups`, keeps 7 | — |

The units are in `deploy/laptop/systemd/`, symlinked into `~/.config/systemd/user/`. Linger starts them at boot without a login.
The laptop never sleeps: the lid is ignored and the sleep targets are masked.

## Ship a change
```bash
git push laptop <branch>                                  # from the Mac; remote = ssh://rohan@192.168.29.132/~/myjobs
ssh rohan@192.168.29.132 '~/myjobs/deploy/laptop/setup.sh' # reinstall, migrate, rebuild web, restart services
```

## Fresh install
```bash
git init ~/myjobs && git -C ~/myjobs config receive.denyCurrentBranch updateInstead   # on the laptop, then push from the Mac
sudo ~/myjobs/deploy/laptop/root-setup.sh   # once: Docker, Node, Chromium libraries, no sleep, linger, ufw
~/myjobs/deploy/laptop/setup.sh             # add --restore <pg_dump file> to load existing data
```

## Operate
- Logs: `journalctl --user -u myjobs-worker -f` (likewise `myjobs-api`, `myjobs-web`).
- Status: `systemctl --user status 'myjobs-*'`; `.venv/bin/myjobs health`; `.venv/bin/myjobs stats`.
- sudo asks for a password, so root steps can't run over a non-interactive SSH session.

## Not done yet
A public URL (e.g. a free Cloudflare Tunnel), off-machine backups, and alerting on `myjobs health`.
