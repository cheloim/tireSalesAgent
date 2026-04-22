# Neumáticos Martinez — Claude Code Project Brief

## What this is
A tire sales agent for "Neumáticos Martinez" (Buenos Aires). Customers chat via WhatsApp, Telegram, or a web interface. A Google Gemini-powered agent handles the conversation, searches inventory, generates quotes, and confirms sales. An internal web dashboard shows live metrics, active chats, confirmed sales, and conversation logs.

## Stack
- **Backend**: Flask (Python) on port 5000 — agent logic, SSE streaming, all `/api/*` and `/webhook/*` routes
- **Frontend server**: Node.js/Express on port 8080 — serves `public/` static files, proxies `/api/*` and `/webhook/*` to Flask
- **LLM**: Google Gemini (`gemini-2.0-flash` via `google-genai` SDK) — cloud API, not local
- **Database**: SQLite at `conversaciones.db` (same directory as `app.py`)
- **Channels**: Web chat, Telegram Bot, WhatsApp (Meta API), Twilio WhatsApp

## File map
```
app.py          Flask app — all routes, SSE streaming, DB access, channel handlers
agent.py        Gemini LLM wrapper — system prompt, procesar_mensaje(), tool execution loop
tools.py        Agent tools — buscar_neumaticos, generar_presupuesto, confirmar_venta, etc.
inventory.py    Static tire catalog + vehicle compatibility map
server.js       Node.js/Express — static files + proxy to Flask
public/
  index.html    Internal dashboard (metrics, active chats, confirmed sales, logs)
  dashboard.js  Dashboard JS — SSE client, chat drawer, sales modal, debug toggle
  dashboard.css Shared dark theme for all pages
  chat.html     Customer-facing web chat (Latin Spanish UI)
  app.js        Web chat JS — message queue/debounce, SSE stream handler
  logs.html     Server logs page (real-time SSE stream)
  logs.js       Logs page JS
```

## Architecture decisions
- **Node proxies Flask**: All HTTP goes through Node (port 8080). Flask is never exposed directly. `request.remote_addr` is always `127.0.0.1` from Flask's perspective.
- **SSE for everything real-time**: Chat responses stream via SSE (`text/event-stream`). Dashboard metrics update via SSE every 4s. Server logs stream via SSE.
- **Session IDs**: Permanent per user (`session_id` = Telegram chat_id, phone number for WA/Twilio, Flask cookie UUID for web). A separate `conversation_id` (UUID) is generated per logical conversation (resets when `len(historial) == 0`).
- **SQLite tables**: `historiales` (last 40 msgs per session), `ventas` (confirmed sales), `conversations` (per-conversation logs with UUID).
- **Message buffering**: TG/WA use `_buffer_message()` with 8s debounce to combine rapid messages. Web chat uses a 3.5s frontend debounce queue (`_msgQueue` in `app.js`) — same UX, different implementation.
- **Human delays**: Backend sleeps 3-9s before sending first response part, 2-3s between parts — simulates real typing.
- **Multi-part responses**: Agent separates parts with `|||`. Each part gets its own bubble with a typing indicator between them.

## Agent behavior (key rules)
- Persona: friendly WhatsApp-style salesperson, short sentences, no chatbot feel
- Locations: `<ubicacion>acassuso</ubicacion>` and `<ubicacion>martinez</ubicacion>` tags get replaced with text links (web) or location messages (TG/WA)
- Images: `<imagen>es32</imagen>` etc. → photo sent on TG, ignored on web
- Personal questions: first time → evasive but natural; if insistent → ignore until back on topic
- Branch questions: inform both locations, send both tags, don't ask which is preferred
- `confirmar_venta` only called on explicit purchase confirmation, never for quotes

## Database path
Always use absolute path — `DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversaciones.db")`. Never relative paths (SSE threads break with relative paths).

## Debug mode
Toggle from the 🐛 button in the dashboard header. Sets `_web_debug_mode` global in `app.py`. When ON, `procesar_mensaje()` uses `_PROMPT_DEBUG` (no restrictions) instead of the production prompt. Resets to OFF on server restart (in-memory only).

## Environment variables (`.env`)
```
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

## Running locally
```bash
# Terminal 1 — Flask
python app.py

# Terminal 2 — Node.js
npm start

# Access
http://localhost:8080        → Dashboard
http://localhost:8080/chat   → Web chat
http://localhost:8080/logs.html → Server logs
```

## Patterns to follow
- **No comments** unless the WHY is non-obvious
- **Spanish** for agent prompt, customer-facing UI (Latin American), and internal logs
- **English** for dashboard UI labels
- CSS uses variables from `dashboard.css` — `--brand`, `--bg`, `--bg2`, `--bg3`, `--border`, `--text`, `--muted`, `--green`, `--radius`, `--font`
- New dashboard panels follow the `.table-section` / `.data-table` pattern
- New drawers/modals reuse `.chat-drawer` / `.sale-modal` patterns already in `dashboard.css`
- Tool calls in agent responses use `<tool>{...}</tool>` format — never `<tool_code>`

## Deployment target
AWS EC2 `t2.micro`, Ubuntu 22.04, nginx reverse proxy + Let's Encrypt SSL. Node.js and Flask run as `systemd` services. SQLite on EBS volume.
