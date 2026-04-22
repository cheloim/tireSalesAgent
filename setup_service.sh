#!/bin/bash
# Instala y habilita el servicio systemd del agente.
# Ejecutar una sola vez en la instancia EC2 como ubuntu.

set -e

APP_DIR="/home/ubuntu/tire_sales_agent"
SERVICE="tire-agent"
WEB_SERVICE="tire-agent-web"

# Instalar dependencias Python
if ! command -v gunicorn &>/dev/null && [ ! -f "$HOME/.local/bin/gunicorn" ]; then
    echo "Instalando dependencias Python..."
    pip install --user -r "$APP_DIR/requirements.txt"
fi

# Instalar dependencias Node.js
if ! command -v node &>/dev/null; then
    echo "Node.js no encontrado. Instalando..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

echo "Instalando dependencias npm..."
cd "$APP_DIR" && npm install --omit=dev

# Copiar y habilitar servicios
sudo cp "$APP_DIR/$SERVICE.service" /etc/systemd/system/
sudo cp "$APP_DIR/$WEB_SERVICE.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" "$WEB_SERVICE"
sudo systemctl start "$SERVICE" "$WEB_SERVICE"

echo ""
echo "Servicios instalados."
echo "  Flask/API:   sudo systemctl status $SERVICE"
echo "  Frontend:    sudo systemctl status $WEB_SERVICE"
echo "  Logs API:    sudo journalctl -u $SERVICE -f"
echo "  Logs Web:    sudo journalctl -u $WEB_SERVICE -f"
echo "  Dashboard:   ssh -L 8080:localhost:8080 ubuntu@<EC2-IP>"
