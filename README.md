# Neumáticos Martinez — Agente de ventas

Agente de ventas conversacional para una gomería, con soporte para Telegram, WhatsApp (Cloud API) y Twilio. Usa Google Gemini como LLM y tiene un panel interno en tiempo real para monitorear conversaciones, ventas y logs del servidor.

## Arquitectura

```
Cliente (Telegram / WhatsApp / Web)
        │
        ▼
Node.js / Express  :3000   ← sirve /public (dashboard)
        │  proxy /api/* y /webhook/*
        ▼
Flask / Python     :5000   ← lógica del agente, webhooks, SSE
        │
        ├── Google Gemini (LLM)
        ├── SQLite  (conversaciones.db)
        └── Notificaciones internas (Telegram / WhatsApp)
```

## Archivos principales

| Archivo | Descripción |
|---|---|
| `app.py` | Servidor Flask: webhooks, sesiones, DB, SSE, dashboard API |
| `agent.py` | Lógica del agente: prompt, herramientas, streaming Gemini |
| `tools.py` | Herramientas del agente: buscar neumáticos, confirmar venta, escalar |
| `inventory.py` | Catálogo de productos (precios y stock) |
| `server.js` | Servidor Node.js: proxy hacia Flask, sirve archivos estáticos |
| `public/` | Dashboard interno (HTML/CSS/JS) |

## Variables de entorno

Copiar `.env.example` como `.env` y completar los valores:

```env
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_VERIFY_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=
NGROK_URL=
TG_NOTIFY_CHAT_ID=
WA_NOTIFY_NUMBER=
```

## Instalación

### Python
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Node.js
```bash
npm install
```

## Ejecución

```bash
# Terminal 1 — backend Flask
source .venv/bin/activate
python app.py

# Terminal 2 — frontend Node.js
npm start
```

El dashboard queda disponible en `http://localhost:3000`.

## Dashboard

- `/` — Métricas en tiempo real, chats activos, ventas y logs de los últimos 7 días
- `/logs.html` — Logs del servidor en tiempo real (SSE)

Cada fila de ventas y de logs de conversación tiene un botón `↓` para descargar el detalle en formato `.log`.

## Canales soportados

| Canal | Entrada | Notas |
|---|---|---|
| Telegram | `/webhook/telegram` | Soporta texto, voz y fotos |
| WhatsApp Cloud API | `/webhook/whatsapp` | Texto e imágenes |
| Twilio (WhatsApp) | `/webhook/twilio` | Texto |
| Web | `/chat` (SSE) | Interfaz web incluida |
