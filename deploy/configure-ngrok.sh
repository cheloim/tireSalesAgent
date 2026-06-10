#!/bin/bash
# Genera el archivo de configuracion de ngrok desde el secret.
# Invocado por el workflow de GitHub Actions.

set -e

mkdir -p ~/.config/ngrok

cat > ~/.config/ngrok/ngrok.yml <<-'EOF'
version: 3
agent:
    authtoken: AUTHTOKEN_PLACEHOLDER
tunnels:
  app:
    proto: http
    addr: 5000
EOF

sed -i "s|AUTHTOKEN_PLACEHOLDER|$(cat /tmp/ngrok_token)|g" ~/.config/ngrok/ngrok.yml
echo "ngrok config creado en ~/.config/ngrok/ngrok.yml"