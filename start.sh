#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GUNICORN="$SCRIPT_DIR/.venv/bin/gunicorn"

if [ ! -f "$GUNICORN" ]; then
    echo "ERROR: venv no encontrado. Corré setup_service.sh primero." >&2
    exit 1
fi

"$GUNICORN" -w 1 -k gthread --threads 4 --timeout 300 app:app -b 0.0.0.0:5000
