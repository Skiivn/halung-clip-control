#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_file="$repo_root/raspberry/config/station.json"
service_file="/etc/systemd/system/halung-edge-agent.service"
run_user="${SUDO_USER:-$(id -un)}"

if [[ ! -f "$config_file" ]]; then
    echo "Missing $config_file"
    echo "Copy raspberry/config/station.example.json to station.json and configure it first."
    exit 1
fi

python3 -m venv "$repo_root/.venv"
mkdir -p "$repo_root/raspberry/data"
chmod 700 "$repo_root/raspberry/data"
chmod 600 "$config_file"

sudo tee "$service_file" >/dev/null <<UNIT
[Unit]
Description=HALUNG Raspberry Edge Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$run_user
WorkingDirectory=$repo_root
ExecStart=$repo_root/.venv/bin/python -m raspberry.agent --config $config_file
Restart=on-failure
RestartSec=3
UMask=0077

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now halung-edge-agent.service
sudo systemctl --no-pager --full status halung-edge-agent.service
