# Tire Sales Agent — CLAUDE.md

## Stack
- **Backend**: Python 3 + Flask (port 5000) — `app.py`
- **LLM**: Google Gemini via `google-genai` SDK — `agent.py` (model: `gemini-flash-latest`)
- **Frontend proxy**: Node.js/Express (port 8080) — `server.js` → proxies `/api/*` to Flask
- **Static files**: `public/` (chat UI + dashboard)
- **DB**: SQLite — `conversaciones.db` (tablas: `historiales`, `ventas`, `conversations`)
- **Start**: `./start.sh` (Gunicorn, 1 worker, gthread) | `python app.py` para debug

## Archivos clave
| Archivo | Rol |
|---|---|
| `agent.py` | Loop Gemini, tool calling custom con `<tool>`, SSE streaming, reintentos |
| `app.py` | Flask: API, webhooks Telegram/WhatsApp/Twilio, dashboard, DB |
| `tools.py` | 5 herramientas: buscar_neumaticos, ver_detalle, verificar_compatibilidad, obtener_recomendaciones, generar_presupuesto + escalar_a_humano + confirmar_venta |
| `inventory.py` | 12 neumáticos Yokohama (N001–N012), vehículos, precios servicios |
| `server.js` | Express proxy: sirve `public/`, proxies `/api/*` |
| `public/index.html` | Chat web (sin carrito, full-width) |
| `public/dashboard.js` | Dashboard: métricas, chats, logs inline |

## Variables de entorno (.env)
```
GEMINI_API_KEY
TELEGRAM_BOT_TOKEN
TG_NOTIFY_CHAT_ID
WHATSAPP_TOKEN / WHATSAPP_PHONE_ID / WHATSAPP_VERIFY_TOKEN
TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_NUMBER
NGROK_URL
WA_NOTIFY_NUMBER
```

## Rutas Flask
- `POST /api/chat` — SSE streaming (canal web)
- `POST /webhook/telegram` — webhook Telegram
- `POST /webhook/twilio` — webhook Twilio/WhatsApp
- `POST /webhook/whatsapp` + `GET /webhook/whatsapp` — Meta Cloud API (WhatsApp directo)
- `GET  /setup/telegram` — registrar webhook Telegram
- `/api/dashboard/*` — métricas, chats, ventas, logs (SSE en `/stream`)
- `/api/logs/stream` — SSE logs del servidor en tiempo real

## Arquitectura del agente
- **Tool calling**: custom regex `<tool>{"name":..,"args":..}</tool>` (no native Gemini function calling)
- **Multi-mensaje**: separador `|||` — backend splitea y envía con delays humanos
- **Delays**: 2–4s antes de typing dots, 3–9s typing por mensaje, 2–3s pausa entre mensajes
- **Historial**: formato OpenAI internamente, convertido a Gemini en cada llamada
- **Compresión**: últimos 8 turnos verbatim, anteriores truncados a 200 chars
- **Estado en memoria**: `_log_buffer` (deque 500), `_web_debug_mode` — requiere 1 solo worker

## Agentes (personas)
Rodrigo, Matías, Valentina, Camila — asignados por sesión, modo debug disponible

## Deployment actual
- ngrok expone Flask local con HTTPS para webhooks
- Gunicorn via `./start.sh` para producción-like local
- Plan futuro: EC2 t3.micro + Nginx + Certbot + systemd

## Convenciones
- Español rioplatense en toda la UI y lógica de negocio
- Sin carrito — presupuesto inline via `generar_presupuesto`
- Precios en pesos argentinos con punto de miles: `$140.090`
- `(?)` nunca `(¿)` en mensajes del agente
