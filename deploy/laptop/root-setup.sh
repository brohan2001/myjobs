#!/usr/bin/env bash
# One-time system setup for running myjobs on a home Ubuntu laptop (D29). Safe to re-run.
#
#   sudo deploy/laptop/root-setup.sh
#
# Installs Docker, Node and Chromium's libraries; keeps the laptop awake with the lid shut; lets user services run
# without a login; opens the feed (:3000) to the home network only. Then run deploy/laptop/setup.sh as your user.
set -euo pipefail

user=${SUDO_USER:?run this with sudo from your normal account}
repo=$(cd "$(dirname "$0")/../.." && pwd)
wifi=$(ip -4 route show default | awk '{print $5; exit}')   # not docker0: Docker adds its own 172.x routes
lan=$(ip -4 route show dev "$wifi" proto kernel | awk '{print $1; exit}')

apt-get update
apt-get install -y docker.io docker-compose-v2 nodejs npm avahi-daemon
systemctl enable --now docker avahi-daemon
usermod -aG docker "$user"

# The browser worker's system libraries
"$repo/.venv/bin/playwright" install-deps chromium

# Never sleep: ignore the lid and disable every suspend path (GNOME's idle suspend included)
mkdir -p /etc/systemd/logind.conf.d /etc/NetworkManager/conf.d
cat > /etc/systemd/logind.conf.d/myjobs.conf <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
EOF
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl kill -s HUP systemd-logind   # reload without ending the desktop session

# Wi-Fi power saving drops idle connections on many laptops
printf '[connection]\nwifi.powersave = 2\n' > /etc/NetworkManager/conf.d/myjobs-wifi-powersave.conf
systemctl reload NetworkManager || true

# Start the user's services at boot, without anyone logging in
loginctl enable-linger "$user"

# Firewall: SSH from anywhere it can reach, the feed from the home network only. The API (:8090), Postgres and
# Redis listen on 127.0.0.1 and stay private.
ufw allow OpenSSH
ufw allow from "${lan:?no home network found}" to any port 3000 proto tcp comment 'myjobs feed (LAN)'
ufw --force enable

echo "Done. Log out and back in (or reboot) so '$user' can use Docker, then run deploy/laptop/setup.sh."
