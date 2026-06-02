#!/bin/bash
# Genera y despliega servicios systemd para tire-agent.
# Este script es invocado por el GitHub Action workflow.

set -e

REPO_DIR="$HOME/tireSalesAgent"
SERVICE_NAME="tire-agent"
WEB_SERVICE_NAME="tire-agent-web"

echo "=== Generar servicios systemd ==="
APP_USER=$(whoami)

cat > /tmp/$SERVICE_NAME.service <<-EOF
[Unit]
Description=Tire Sales Agent (Gunicorn/Flask)
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$REPO_DIR
EnvironmentFile=$REPO_DIR/.env
ExecStart=$REPO_DIR/.venv/bin/gunicorn -w 1 -k gthread --threads 4 --timeout 300 app:app -b 0.0.0.0:5000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tire-agent

[Install]
WantedBy=multi-user.target
EOF

cat > /tmp/$WEB_SERVICE_NAME.service <<-EOF
[Unit]
Description=Tire Sales Agent – Frontend (Node.js/Express)
After=network.target tire-agent.service
Requires=tire-agent.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/node server.js
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tire-agent-web

[Install]
WantedBy=multi-user.target
EOF

sudo cp /tmp/$SERVICE_NAME.service /etc/systemd/system/
sudo cp /tmp/$WEB_SERVICE_NAME.service /etc/systemd/system/
sudo systemctl daemon-reload

echo "=== Restart servicios ==="
sudo systemctl restart tire-agent
sudo systemctl restart tire-agent-web

echo "=== Health check ==="
sleep 3
curl -sf http://localhost:5000/api/estado && echo " API OK" || echo "WARN: API no responde"

echo "=== Estado ==="
sudo systemctl is-active tire-agent    && echo "tire-agent OK"     || echo "tire-agent FAIL"
sudo systemctl is-active tire-agent-web && echo "tire-agent-web OK" || echo "tire-agent-web FAIL"