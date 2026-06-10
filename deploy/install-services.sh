#!/bin/bash
# Genera y despliega servicios systemd para tire-agent.
# Este script es invocado por el GitHub Action workflow.
# Soporta: Ubuntu, Debian, CentOS, RHEL, Rocky, Alma, Fedora

set -e

REPO_DIR="$HOME/tireSalesAgent"
SERVICE_NAME="tire-agent"
WEB_SERVICE_NAME="tire-agent-web"

echo "=== Detectar SO ==="
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VER="$VERSION_ID"
else
    echo "ERROR: No se puede detectar el sistema operativo" >&2
    exit 1
fi

echo "  SO: $OS_ID $VERSION_ID"

case "$OS_ID" in
    ubuntu|debian)
        PKG_MGR="apt-get"
        PYTHON_PKG="python3.11 python3.11-venv python3.11-dev"
        NODE_SETUP="curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs"
        ;;
    centos|rhel|rocky|alma)
        PKG_MGR="yum"
        PYTHON_PKG="python311 python311-venv python311-devel"
        NODE_SETUP="curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash - && sudo yum install -y nodejs"
        ;;
    fedora)
        PKG_MGR="dnf"
        PYTHON_PKG="python311 python311-venv python311-devel"
        NODE_SETUP="curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash - && sudo dnf install -y nodejs"
        ;;
    *)
        echo "ERROR: OS no soportada: $OS_ID" >&2
        exit 1
        ;;
esac

echo "=== Generar servicios systemd ==="
APP_USER=$(whoami)
NODE_BIN=$(cat /tmp/node_path.txt 2>/dev/null | grep NODE_BIN | cut -d= -f2 || echo "/usr/bin/node")
echo "  Node bin: $NODE_BIN"

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
ExecStart=${NODE_BIN} server.js
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

echo "=== Logs tire-agent ==="
journalctl -u tire-agent --no-pager -n 10 || true

echo "=== Logs tire-agent-web ==="
journalctl -u tire-agent-web --no-pager -n 10 || true

echo "=== Estado ==="
sudo systemctl is-active tire-agent    || { echo "tire-agent FAIL"; exit 1; }
sudo systemctl is-active tire-agent-web || { echo "tire-agent-web FAIL"; exit 1; }
echo "tire-agent OK"
echo "tire-agent-web OK"

echo "=== Instalar ngrok ==="
if ! command -v ngrok &>/dev/null; then
    echo "Descargando ngrok..."
    curl -fsSL https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz -o /tmp/ngrok.tgz
    sudo tar -xzf /tmp/ngrok.tgz -C /usr/local/bin
    rm /tmp/ngrok.tgz
fi

echo "Instalando servicio ngrok..."
sudo ngrok service install --config ~/.config/ngrok/ngrok.yml
sudo systemctl restart ngrok

echo "=== Logs ngrok ==="
journalctl -u ngrok --no-pager -n 10 || true

echo "=== Estado ngrok ==="
sudo systemctl is-active ngrok || { echo "ngrok FAIL"; exit 1; }
echo "ngrok OK"