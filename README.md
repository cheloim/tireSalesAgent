# Tire Sales Agent — Agente de ventas para gomería

Agente de ventas conversacional para una gomería, con soporte para Telegram, WhatsApp (Cloud API) y Twilio. Usa Google Gemini como LLM y tiene un panel interno en tiempo real para monitorear conversaciones, ventas y logs del servidor.

## Arquitectura

```
Cliente (Telegram / WhatsApp / Web)
        │
        ▼
Node.js / Express  :8080   ← sirve /public (dashboard + chat web)
        │  proxy /api/* y /webhook/*
        ▼
Flask / Python     :5000   ← lógica del agente, webhooks, SSE
        │
        ├── Google Gemini (LLM)
        ├── SQLite  (neumáticos.db)
        └── Notificaciones internas (Telegram / WhatsApp)
```

## Archivos principales

| Archivo | Descripción |
|---|---|
| `app.py` | Servidor Flask: webhooks, sesiones, DB, SSE, dashboard API |
| `agent.py` | Lógica del agente: prompt, herramientas, streaming Gemini |
| `tools.py` | Herramientas del agente: buscar neumáticos, confirmar venta, escalar |
| `inventory.py` | Catálogo de productos (12 neumáticos Yokohama, precios y stock) |
| `server.js` | Servidor Node.js: proxy hacia Flask, sirve archivos estáticos |
| `public/` | Dashboard interno y chat web (HTML/CSS/JS) |
| `start.sh` | Script de inicio con Gunicorn (1 worker, gthread) |

## Variables de entorno

Copiar `.env.example` como `.env` y completar los valores:

```env
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
TG_NOTIFY_CHAT_ID=
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_VERIFY_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_WHATSAPP_NUMBER=
NGROK_URL=
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
./start.sh
```

Esto inicia Gunicorn con 1 worker gthread en puerto 5000. El dashboard queda disponible en `http://localhost:8080`.

Para debug:
```bash
source .venv/bin/activate
python app.py
```

## Dashboard

- `/` — Métricas en tiempo real, chats activos, ventas y logs de los últimos 7 días
- `/logs.html` — Logs del servidor en tiempo real (SSE)
- `/api/logs/stream` — Endpoint SSE para logs en tiempo real

Cada fila de ventas y de logs de conversación tiene un botón `↓` para descargar el detalle en formato `.log`.

## Canales soportados

| Canal | Endpoint | Notas |
|---|---|---|
| Telegram | `POST /webhook/telegram` | Soporta texto, voz y fotos |
| WhatsApp Cloud API | `POST /webhook/whatsapp` + `GET /webhook/whatsapp` | Texto e imágenes |
| Twilio (WhatsApp) | `POST /webhook/twilio` | Texto |
| Web | `POST /api/chat` (SSE) | Interfaz chat web incluida |

## Agentes (personas)

El sistema asigna automáticamente uno de los siguientes agentes por sesión:
- Rodrigo
- Matías
- Valentina
- Camila

Cada agente puede operar en modo debug para pruebas.

## Arquitectura del agente

- **Tool calling**: custom regex `<tool>{"name":..,"args":..}</tool>` (no native Gemini function calling)
- **Multi-mensaje**: separador `|||` — el backend splitea y envía con delays humanos
- **Delays**: 2–4s antes de typing dots, 3–9s typing por mensaje, 2–3s pausa entre mensajes
- **Historial**: formato OpenAI internamente, convertido a Gemini en cada llamada
- **Compresión**: últimos 8 turnos verbatim, anteriores truncados a 200 chars
- **Estado en memoria**: `_log_buffer` (deque 500), `_web_debug_mode`

## Convenciones

- Idioma: español rioplatense en toda la UI y lógica de negocio
- Precios: pesos argentinos con punto de miles (ej: `$140.090`)
- Sin carrito — presupuesto inline via `generar_presupuesto`
- Separador de mensajes: `(?)` nunca `(¿)`

## Base de datos

Tablas SQLite (`neumáticos.db`):
- `historiales` — historial de conversaciones
- `ventas` — registro de ventas confirmadas
- `conversations` — sesiones de chat
