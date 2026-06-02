#!/bin/bash
# Instala y habilita el servicio systemd del agente.
# Ejecutar una sola vez en la instancia EC2 como ubuntu.

set -e

APP_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="tire-agent"
WEB_SERVICE_NAME="tire-agent-web"

echo "=== Configuracion detectada ==="
echo "  Usuario: $APP_USER"
echo "  Directorio: $SCRIPT_DIR"
echo ""

# Verificar que python3-venv esté instalado
if ! python3.11 -m venv --help &>/dev/null; then
    echo "python3.11 no encontrado. Instalando..."
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
fi

echo "Configurando virtualenv..."
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    python3.11 -m venv "$SCRIPT_DIR/.venv"
fi
"$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip -q
"$SCRIPT_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q

# Instalar dependencias Node.js
if ! command -v node &>/dev/null; then
    echo "Node.js no encontrado. Instalando..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "Instalando dependencias npm..."
cd "$SCRIPT_DIR" && npm install --omit=dev

# Generar y copiar servicio tire-agent
echo "Generando servicios systemd..."
cat > /tmp/$SERVICE_NAME.service <<EOF
[Unit]
Description=Tire Sales Agent (Gunicorn/Flask)
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$SCRIPT_DIR
EnvironmentFile=$SCRIPT_DIR/.env
ExecStart=$SCRIPT_DIR/.venv/bin/gunicorn -w 1 -k gthread --threads 4 --timeout 300 app:app -b 0.0.0.0:5000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tire-agent

[Install]
WantedBy=multi-user.target
EOF

# Generar y copiar servicio tire-agent-web
cat > /tmp/$WEB_SERVICE_NAME.service <<EOF
[Unit]
Description=Tire Sales Agent – Frontend (Node.js/Express)
After=network.target tire-agent.service
Requires=tire-agent.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$SCRIPT_DIR
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
sudo systemctl enable "$SERVICE_NAME" "$WEB_SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME" "$WEB_SERVICE_NAME"

echo ""
echo "=== Servicios instalados ==="
echo "  Usuario: $APP_USER"
echo "  Directorio: $SCRIPT_DIR"
echo "  Flask/API:   sudo systemctl status $SERVICE_NAME"
echo "  Frontend:    sudo systemctl status $WEB_SERVICE_NAME"
echo "  Logs API:    journalctl -u $SERVICE_NAME -f"
echo "  Logs Web:    journalctl -u $WEB_SERVICE_NAME -f"
echo "  Dashboard:   ssh -L 8080:localhost:8080 ubuntu@<EC2-IP>"