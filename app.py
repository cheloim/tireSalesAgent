"""Servidor web Flask para el Agente de Ventas de Neumáticos."""

import collections
import json
import logging
import os
import random
import re
import sqlite3
import threading
import time
import uuid

import requests as http
from flask import Flask, Response, jsonify, request, send_from_directory, session, stream_with_context

from agent import AGENTES, MODELO_DEFAULT, TEMPERATURA, PROMPT_VERSION, get_prompt_sistema, procesar_mensaje, transcribir_audio, verificar_gemini

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Log buffer en memoria ─────────────────────────────────────
_log_buffer:  collections.deque = collections.deque(maxlen=500)
_log_counter: int = 0
_log_lock = threading.Lock()


class _MemHandler(logging.Handler):
    def emit(self, record):
        global _log_counter
        try:
            line = self.format(record)
            with _log_lock:
                _log_buffer.append({
                    "n":     _log_counter,
                    "ts":    record.created,
                    "level": record.levelname,
                    "msg":   line,
                })
                _log_counter += 1
        except Exception:
            pass


_mem_handler = _MemHandler()
_mem_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s"))
logging.getLogger().addHandler(_mem_handler)

app = Flask(__name__)
app.secret_key = "neumaticos-plus-secret-key-2024"

# Modelo a usar (configurable)
MODELO_LLM = MODELO_DEFAULT

_web_debug_mode = False

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

WA_TOKEN        = os.environ.get("WHATSAPP_TOKEN", "")
WA_PHONE_ID     = os.environ.get("WHATSAPP_PHONE_ID", "")
WA_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
WA_API          = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"

TWILIO_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")
NGROK_URL     = os.environ.get("NGROK_URL", "").rstrip("/")

TG_NOTIFY_CHAT_ID = os.environ.get("TG_NOTIFY_CHAT_ID", "")
WA_NOTIFY_NUMBER  = os.environ.get("WA_NOTIFY_NUMBER", "")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conversaciones.db")


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS historiales (
                session_id  TEXT PRIMARY KEY,
                mensajes    TEXT NOT NULL DEFAULT '[]',
                actualizado TEXT,
                agente      TEXT,
                canal       TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ventas (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                agente     TEXT,
                marca      TEXT,
                modelo     TEXT,
                medida     TEXT,
                cantidad   INTEGER,
                total      REAL,
                cliente    TEXT,
                sucursal   TEXT,
                fecha      TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                session_id      TEXT,
                agente          TEXT,
                canal           TEXT,
                mensajes        TEXT NOT NULL DEFAULT '[]',
                iniciado        TEXT,
                actualizado     TEXT
            )
        """)
        # migraciones sobre tabla existente
        cols = {r[1] for r in conn.execute("PRAGMA table_info(historiales)").fetchall()}
        for col, tipo in [("agente", "TEXT"), ("canal", "TEXT")]:
            if col not in cols:
                conn.execute(f"ALTER TABLE historiales ADD COLUMN {col} {tipo}")
        cols_conv = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        for col, tipo in [
            ("modelo", "TEXT"), ("temperatura", "REAL"), ("prompt_version", "TEXT"),
            ("debug", "INTEGER DEFAULT 0"),
            ("confianza", "TEXT"), ("contexto", "INTEGER"), ("memoria", "INTEGER"), ("logica_negocio", "TEXT"),
        ]:
            if col not in cols_conv:
                conn.execute(f"ALTER TABLE conversations ADD COLUMN {col} {tipo}")
        cols_hist = {r[1] for r in conn.execute("PRAGMA table_info(historiales)").fetchall()}
        if "debug" not in cols_hist:
            conn.execute("ALTER TABLE historiales ADD COLUMN debug INTEGER DEFAULT 0")
        conn.commit()

_init_db()


def obtener_historial(session_id: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT mensajes FROM historiales WHERE session_id = ?", (session_id,)
        ).fetchone()
        return json.loads(row[0]) if row else []


def obtener_conversation_id(session_id: str) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT conversation_id FROM conversations WHERE session_id = ? ORDER BY iniciado DESC LIMIT 1",
            (session_id,)
        ).fetchone()
    return row[0] if row else str(uuid.uuid4())


def guardar_historial(
    session_id: str,
    historial: list[dict],
    canal: str | None = None,
    conversation_id: str | None = None,
    modelo: str | None = None,
    temperatura: float | None = None,
    prompt_version: str | None = None,
    debug: bool = False,
    confianza: str | None = None,
    contexto: int | None = None,
    memoria: int | None = None,
    logica_negocio: str | None = None,
):
    datos = json.dumps(historial[-40:], ensure_ascii=False)
    debug_int = 1 if debug else 0
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO historiales (session_id, mensajes, actualizado, canal, debug)
            VALUES (?, ?, datetime('now', 'localtime'), ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                mensajes    = excluded.mensajes,
                actualizado = excluded.actualizado,
                canal       = COALESCE(historiales.canal, excluded.canal),
                debug       = MAX(historiales.debug, excluded.debug)
        """, (session_id, datos, canal, debug_int))
        if conversation_id:
            row = conn.execute("SELECT agente FROM historiales WHERE session_id = ?", (session_id,)).fetchone()
            agente_nombre = row[0] if row else None
            conn.execute("""
                INSERT INTO conversations
                    (conversation_id, session_id, agente, canal, mensajes, iniciado, actualizado,
                     modelo, temperatura, prompt_version, debug,
                     confianza, contexto, memoria, logica_negocio)
                VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'), ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    mensajes       = excluded.mensajes,
                    actualizado    = excluded.actualizado,
                    agente         = COALESCE(conversations.agente, excluded.agente),
                    canal          = COALESCE(conversations.canal, excluded.canal),
                    modelo         = COALESCE(conversations.modelo, excluded.modelo),
                    temperatura    = COALESCE(conversations.temperatura, excluded.temperatura),
                    prompt_version = COALESCE(conversations.prompt_version, excluded.prompt_version),
                    debug          = MAX(conversations.debug, excluded.debug),
                    confianza      = COALESCE(excluded.confianza, conversations.confianza),
                    contexto       = COALESCE(excluded.contexto, conversations.contexto),
                    memoria        = COALESCE(excluded.memoria, conversations.memoria),
                    logica_negocio = CASE
                        WHEN conversations.logica_negocio IS NULL THEN excluded.logica_negocio
                        WHEN excluded.logica_negocio IS NULL THEN conversations.logica_negocio
                        ELSE conversations.logica_negocio || ',' || excluded.logica_negocio
                    END
            """, (conversation_id, session_id, agente_nombre, canal, datos, modelo, temperatura, prompt_version, debug_int,
                  confianza, contexto, memoria, logica_negocio))
        conn.commit()


def obtener_o_asignar_agente(session_id: str) -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT agente FROM historiales WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row and row[0]:
            return next((a for a in AGENTES if a["nombre"] == row[0]), AGENTES[0])
        agente = random.choice(AGENTES)
        conn.execute("""
            INSERT INTO historiales (session_id, mensajes, agente, actualizado)
            VALUES (?, '[]', ?, datetime('now', 'localtime'))
            ON CONFLICT(session_id) DO UPDATE SET agente = excluded.agente
        """, (session_id, agente["nombre"]))
        conn.commit()
        return agente


def obtener_session_id() -> str:
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


@app.route("/api/estado")
def estado():
    """Verifica el estado de Ollama y retorna info del sistema."""
    disponible, mensaje = verificar_gemini(MODELO_LLM)
    return jsonify({
        "ollama_disponible": disponible,
        "mensaje": mensaje,
        "modelo": MODELO_LLM,
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    """Endpoint principal de chat con streaming SSE."""
    datos = request.get_json()
    if not datos or "mensaje" not in datos:
        return jsonify({"error": "Se requiere el campo 'mensaje'"}), 400

    mensaje_usuario = datos["mensaje"].strip()
    if not mensaje_usuario:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    session_id      = obtener_session_id()
    historial       = obtener_historial(session_id)
    agente          = obtener_o_asignar_agente(session_id)
    conversation_id = obtener_conversation_id(session_id)

    def generar():
        texto_completo = []
        meta = {}

        try:
            for chunk in procesar_mensaje(mensaje_usuario, historial, session_id, MODELO_LLM, agente, debug=_web_debug_mode, meta=meta):
                texto_completo.append(chunk)

            respuesta_completa = _expandir_ubicaciones_web(limpiar_respuesta("".join(texto_completo)))

            if respuesta_completa:
                partes = [p.strip() for p in respuesta_completa.split("|||") if p.strip()]

                for i, parte in enumerate(partes):
                    palabras = len(parte.split())

                    if i == 0:
                        # Primera respuesta: el typing indicator ya está visible desde el frontend.
                        # Pausa de "escritura" proporcional al largo del mensaje.
                        delay = random.uniform(3.0, 5.0) + (palabras * random.uniform(0.06, 0.10))
                        delay = min(delay, 9.0)
                        time.sleep(delay)
                    else:
                        # Entre mensajes: pausa de "lectura", luego typing indicator, luego pausa de escritura.
                        time.sleep(random.uniform(2.0, 3.0))   # pausa de "lectura"
                        yield "data: {\"tipo\": \"typing\"}\n\n"
                        delay = random.uniform(3.0, 5.0) + (palabras * random.uniform(0.05, 0.09))
                        delay = min(delay, 9.0)
                        time.sleep(delay)

                    data = json.dumps({"tipo": "texto", "contenido": parte}, ensure_ascii=False)
                    yield f"data: {data}\n\n"

            if respuesta_completa:
                historial.append({"role": "user", "content": mensaje_usuario})
                historial.append({"role": "assistant", "content": respuesta_completa})
                guardar_historial(session_id, historial, conversation_id=conversation_id,
                                  modelo=MODELO_LLM, temperatura=TEMPERATURA, prompt_version=PROMPT_VERSION,
                                  debug=_web_debug_mode,
                                  confianza=meta.get("confianza"),
                                  contexto=meta.get("contexto"),
                                  memoria=meta.get("memoria"),
                                  logica_negocio=",".join(meta.get("logica_negocio") or []) or None)

        except GeneratorExit:
            return
        except Exception as e:
            logger.error(f"Error en streaming: {e}")

        yield "data: {\"tipo\": \"fin\"}\n\n"

    def generar_seguro():
        try:
            yield from generar()
        except RuntimeError as e:
            if "generator ignored GeneratorExit" not in str(e):
                raise

    return Response(
        stream_with_context(generar_seguro()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/imagenes/<path:filename>")
def servir_imagen(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "public/imagenes"), filename)


@app.route("/api/limpiar", methods=["POST"])
def limpiar():
    """Limpia el historial de conversación."""
    session_id = obtener_session_id()
    guardar_historial(session_id, [])
    return jsonify({"mensaje": "Conversación reiniciada."})


@app.route("/api/modelo", methods=["POST"])
def cambiar_modelo():
    """Cambia el modelo de Ollama a usar."""
    global MODELO_LLM
    datos = request.get_json()
    if not datos or "modelo" not in datos:
        return jsonify({"error": "Se requiere el campo 'modelo'"}), 400

    MODELO_LLM = datos["modelo"]
    return jsonify({"mensaje": f"Modelo cambiado a: {MODELO_LLM}", "modelo": MODELO_LLM})


# ── Notificaciones internas de venta ─────────────────────────

def _enviar_notificacion(texto: str):
    """Manda texto a TG y WA de notificaciones, en chunks si es necesario."""
    CHUNK = 4000
    if TG_NOTIFY_CHAT_ID:
        for i in range(0, len(texto), CHUNK):
            tg_send_message(int(TG_NOTIFY_CHAT_ID), texto[i:i + CHUNK])
    if WA_NOTIFY_NUMBER:
        for i in range(0, len(texto), CHUNK):
            try:
                http.post(WA_API,
                    headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
                    json={
                        "messaging_product": "whatsapp",
                        "to": WA_NOTIFY_NUMBER,
                        "type": "text",
                        "text": {"body": texto[i:i + CHUNK]},
                    }, timeout=10)
            except Exception as e:
                logger.error(f"Error enviando notificación WA: {e}")


def notificar_dot(session_id: str, neumaticos: str = ""):
    from datetime import datetime
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")

    if session_id.startswith("wa_"):
        contacto = session_id[3:]
    elif session_id.startswith("twilio_"):
        contacto = session_id[7:]
    elif session_id.isdigit():
        contacto = f"Telegram ID {session_id}"
    else:
        contacto = "Web (sin teléfono)"

    lineas = filter(None, [
        "ℹ SOLICITUD DE DOT",
        f"Motivo:    Solicitud de DOT",
        f"Neumático: {neumaticos}" if neumaticos else None,
        f"Contacto:  {contacto}",
        f"Fecha:     {fecha}",
    ])
    _enviar_notificacion("\n".join(lineas))


def notificar_escalado(session_id: str, motivo: str, historial: list[dict]):
    from datetime import datetime
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    alerta = "\n".join(filter(None, [
        "⚠ DERIVACIÓN A HUMANO",
        f"Sesión:  {session_id}",
        f"Motivo:  {motivo}" if motivo else None,
        f"Fecha:   {fecha}",
    ]))
    _enviar_notificacion(alerta)

    if historial:
        lineas = []
        for msg in historial:
            rol = "Cliente" if msg["role"] == "user" else "Rodrigo"
            lineas.append(f"[{rol}] {msg['content'][:600]}")
        _enviar_notificacion("Conversación:\n\n" + "\n\n".join(lineas))


def notificar_venta_interna(neumatico: dict, cantidad: int, nombre_cliente: str, sucursal: str, notas: str, agente: str = ""):
    from datetime import datetime
    fecha = datetime.now().strftime("%d/%m/%Y %H:%M")
    total = neumatico["precio"] * cantidad
    lineas = [
        "PRESUPUESTO CONFIRMADO",
        f"Modelo:   {neumatico['marca']} {neumatico['modelo']}",
        f"Medida:   {neumatico['medida']}",
        f"Cantidad: {cantidad}",
        f"Total:    ${total:,.0f}",
    ]
    if agente:
        lineas.append(f"Agente:   {agente}")
    if nombre_cliente:
        lineas.append(f"Cliente:  {nombre_cliente}")
    if sucursal:
        lineas.append(f"Sucursal: {sucursal.capitalize()}")
    if notas:
        lineas.append(f"Notas:    {notas}")
    lineas.append(f"Fecha:    {fecha}")
    _enviar_notificacion("\n".join(lineas))


def registrar_venta(session_id: str, agente: str, neumatico: dict, cantidad: int, cliente: str, sucursal: str):
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("""
            SELECT id FROM ventas
            WHERE session_id = ? AND marca = ? AND modelo = ? AND medida = ? AND cantidad = ?
              AND fecha >= datetime('now', 'localtime', '-5 minutes')
        """, (session_id, neumatico.get("marca", ""), neumatico.get("modelo", ""),
              neumatico.get("medida", ""), cantidad)).fetchone()
        if existing:
            logger.warning(f"Venta duplicada ignorada [{session_id}]")
            return
        conn.execute("""
            INSERT INTO ventas (session_id, agente, marca, modelo, medida, cantidad, total, cliente, sucursal)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, agente,
            neumatico.get("marca", ""), neumatico.get("modelo", ""), neumatico.get("medida", ""),
            cantidad, neumatico.get("precio", 0) * cantidad,
            cliente, sucursal,
        ))
        conn.commit()


# ── Message buffer (debounce) ────────────────────────────────

_msg_buffers: dict[str, dict] = {}
_buf_lock = threading.Lock()
MSG_BUFFER_DELAY = 8  # segundos a esperar antes de procesar


def _buffer_message(session_id: str, text: str, flush_fn):
    """Agrega texto al buffer y (re)inicia el timer. Cuando vence, llama flush_fn(texto_combinado)."""
    with _buf_lock:
        buf = _msg_buffers.setdefault(session_id, {"messages": [], "timer": None})
        buf["messages"].append(text)
        if buf["timer"]:
            buf["timer"].cancel()

        def _flush():
            with _buf_lock:
                msgs = _msg_buffers.pop(session_id, {}).get("messages", [])
            if msgs:
                try:
                    flush_fn("\n".join(msgs))
                except Exception as e:
                    logger.error(f"Error en flush de buffer [{session_id}]: {e}", exc_info=True)

        timer = threading.Timer(MSG_BUFFER_DELAY, _flush)
        buf["timer"] = timer
        timer.start()


# ── Telegram helpers ──────────────────────────────────────────

def tg_descargar_audio(file_id: str) -> bytes | None:
    def _intentar() -> bytes:
        res = http.get(f"{TELEGRAM_API}/getFile", params={"file_id": file_id}, timeout=10)
        file_path = res.json()["result"]["file_path"]
        audio_res = http.get(
            f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}", timeout=30
        )
        return audio_res.content

    for intento in range(5):
        try:
            return _intentar()
        except Exception as e:
            if "Name or service not known" not in str(e):
                logger.error(f"Error descargando audio de Telegram: {e}")
                return None
            logger.warning(f"DNS no resolvió (intento {intento + 1}/5), reintentando en 20s")
            time.sleep(20)

    return None


def _procesar_audio_diferido(chat_id: int, file_id: str, session_id: str, modelo: str):
    logger.info(f"Reintentando audio diferido para chat {chat_id}")
    audio_bytes = tg_descargar_audio(file_id)
    if not audio_bytes:
        logger.error(f"Audio diferido fallido tras reintentos [{chat_id}]")
        return

    text = transcribir_audio(audio_bytes, modelo) or ""
    if not text:
        logger.error(f"Transcripción diferida fallida [{chat_id}]")
        return

    historial       = obtener_historial(session_id)
    conversation_id = obtener_conversation_id(session_id)
    tg_send_typing(chat_id)
    meta_audio = {}
    try:
        chunks    = list(procesar_mensaje(text, historial, session_id, modelo, meta=meta_audio))
        respuesta = "".join(chunks).strip()
    except Exception as e:
        logger.error(f"Error procesando audio diferido: {e}")
        return

    if not respuesta:
        return

    partes = [p.strip() for p in respuesta.split("|||") if p.strip()]
    for i, parte in enumerate(partes):
        if i > 0:
            time.sleep(random.uniform(1.5, 2.5))
            tg_send_typing(chat_id)
            time.sleep(random.uniform(1.5, 3.0))
        tg_send_message(chat_id, parte)

    historial.append({"role": "user",      "content": text})
    historial.append({"role": "assistant", "content": respuesta})
    guardar_historial(session_id, historial, conversation_id=conversation_id,
                      modelo=MODELO_LLM, temperatura=TEMPERATURA, prompt_version=PROMPT_VERSION,
                      debug=False,
                      confianza=meta_audio.get("confianza"), contexto=meta_audio.get("contexto"),
                      memoria=meta_audio.get("memoria"),
                      logica_negocio=",".join(meta_audio.get("logica_negocio") or []) or None)


IMAGENES_MODELOS = {
    "es32":  os.path.join(os.path.dirname(__file__), "public/imagenes/es32.webp"),
    "ae61":  os.path.join(os.path.dirname(__file__), "public/imagenes/ae61.webp"),
    "ac02a": os.path.join(os.path.dirname(__file__), "public/imagenes/ac02a.webp"),
}

_IMAGEN_RE    = re.compile(r"<imagen>(es32|ae61|ac02a)</imagen>", re.IGNORECASE)
_UBICACION_RE       = re.compile(r"<ubicacion>(acassuso|martinez)</ubicacion>", re.IGNORECASE)
_UBICACION_RESTO_RE = re.compile(r"</?ubicacion[^>]*>?", re.IGNORECASE)
_THOUGHT_RE   = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)
_HTML_TAG_RE  = re.compile(r"</?(?!tool|imagen|ubicacion)\w+[^>]*>", re.IGNORECASE)

_mensajes_procesados: dict[str, float] = {}
_DEDUP_TTL = 300  # segundos


def _ya_procesado(msg_id: str) -> bool:
    ahora = time.time()
    _mensajes_procesados.update({k: v for k, v in _mensajes_procesados.items() if ahora - v < _DEDUP_TTL})
    if msg_id in _mensajes_procesados:
        return True
    _mensajes_procesados[msg_id] = ahora
    return False


def limpiar_respuesta(text: str) -> str:
    text = _THOUGHT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return text.strip()


UBICACIONES = {
    "acassuso": {
        "lat": -34.479471, "lng": -58.5073362,
        "nombre":    "Neumáticos Martinez - Acassuso",
        "direccion": "Av. Santa Fe 704, B1640 Acassuso, Buenos Aires",
        "maps_url":  "https://maps.app.goo.gl/bKdFupLX1jiJqjzg9",
    },
    "martinez": {
        "lat": -34.4867215, "lng": -58.5018529,
        "nombre":    "Neumáticos Martinez - Martínez",
        "direccion": "Av. Santa Fe 1628, B1640IFQ Martínez, Buenos Aires",
        "maps_url":  "https://maps.app.goo.gl/vx2WDyoj72rUe9Ju8",
    },
}


def _expandir_ubicaciones_web(text: str) -> str:
    for key, loc in UBICACIONES.items():
        tag = f"<ubicacion>{key}</ubicacion>"
        repl = f"\n📍 {loc['nombre']}\n{loc['direccion']}\n{loc['maps_url']}"
        text = re.sub(re.escape(tag), repl, text, flags=re.IGNORECASE)
    return _UBICACION_RESTO_RE.sub("", text).strip()


def tg_send_photo(chat_id: int, modelo: str):
    path = IMAGENES_MODELOS.get(modelo.lower())
    if not path or not os.path.exists(path):
        logger.warning(f"Imagen no encontrada para modelo: {modelo}")
        return
    try:
        with open(path, "rb") as f:
            http.post(f"{TELEGRAM_API}/sendPhoto",
                      data={"chat_id": chat_id},
                      files={"photo": f}, timeout=20)
    except Exception as e:
        logger.error(f"Error enviando imagen Telegram: {e}")


def tg_send_location(chat_id: int, sucursal: str):
    loc = UBICACIONES.get(sucursal.lower())
    if not loc:
        return
    try:
        url = loc.get("maps_url") or f"https://maps.google.com/?q={loc['lat']},{loc['lng']}"
        tg_send_message(chat_id, f"{loc['nombre']}\n{loc['direccion']}\n{url}")
    except Exception as e:
        logger.error(f"Error enviando ubicación Telegram: {e}")


def tg_send_typing(chat_id: int):
    try:
        http.post(f"{TELEGRAM_API}/sendChatAction",
                  json={"chat_id": chat_id, "action": "typing"}, timeout=5)
    except Exception:
        pass


def tg_send_message(chat_id: int, text: str):
    try:
        http.post(f"{TELEGRAM_API}/sendMessage",
                  json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        logger.error(f"Error enviando mensaje Telegram: {e}")


@app.route("/webhook/telegram", methods=["POST"])
def telegram_webhook():
    update  = request.get_json(silent=True) or {}
    logger.info(f"TG update keys: {list(update.keys())}")
    message = update.get("message") or update.get("edited_message")
    if not message:
        return "", 200

    chat_id = message["chat"]["id"]
    msg_id  = f"tg_{chat_id}_{message.get('message_id')}"
    logger.info(f"TG msg_id={msg_id} keys={list(message.keys())}")
    if _ya_procesado(msg_id):
        logger.info(f"TG duplicado ignorado: {msg_id}")
        return "", 200
    text    = (message.get("text") or message.get("caption") or "").strip()
    logger.info(f"TG text='{text[:100]}' reply={bool(message.get('reply_to_message'))}")

    reply = message.get("reply_to_message")
    if reply and text:
        reply_text = (reply.get("text") or reply.get("caption") or "").strip()[:300]
        if reply_text:
            historial_actual = obtener_historial(str(chat_id))
            ya_en_contexto = any(reply_text[:100] in m.get("content", "") for m in historial_actual[-10:])
            if not ya_en_contexto:
                text = f"{text} [contexto del mensaje al que respondés: {reply_text}]"

    voice = message.get("voice") or (reply or {}).get("voice")
    if voice:
        tg_send_typing(chat_id)
        audio_bytes = tg_descargar_audio(voice["file_id"])
        if not audio_bytes:
            tg_send_message(chat_id, "Ahora mismo no puedo escuchar audios, estoy un poco ocupado. Esperame un ratito que te respondo.")
            threading.Timer(300, _procesar_audio_diferido, args=(chat_id, voice["file_id"], str(chat_id), MODELO_LLM)).start()
            return "", 200
        text = transcribir_audio(audio_bytes, MODELO_LLM) or ""
        if not text:
            tg_send_message(chat_id, "No se escucha bien el audio. Me lo mandás de nuevo o me escribís?")
            return "", 200
        logger.info(f"Audio transcripto [{chat_id}]: {text}")

    if not text or text.startswith("/"):
        return "", 200

    session_id = str(chat_id)
    _buffer_message(session_id, text, lambda t: _procesar_tg(chat_id, session_id, t))
    return "", 200


def _procesar_tg(chat_id: int, session_id: str, text: str):
    historial       = obtener_historial(session_id)
    conversation_id = obtener_conversation_id(session_id)
    agente          = obtener_o_asignar_agente(session_id)
    logger.info(f"TG mensaje procesado [{chat_id}] agente={agente['nombre']}: {text[:300]}")

    tg_send_typing(chat_id)

    respuesta = ""
    meta_tg = {}
    for intento in range(4):
        try:
            chunks    = list(procesar_mensaje(text, historial, session_id, MODELO_LLM, agente, meta=meta_tg))
            respuesta = limpiar_respuesta("".join(chunks))
            break
        except Exception as e:
            logger.warning(f"Error LLM (intento {intento + 1}/4): {e}")
            if intento < 3:
                time.sleep(60)
                tg_send_typing(chat_id)
            else:
                logger.error(f"LLM falló tras 4 intentos [{chat_id}]")
                tg_send_message(chat_id, "Perdoná, tuve un problema. Intentá de nuevo en un momento.")
                return

    if not respuesta:
        return

    imagen_match    = _IMAGEN_RE.search(respuesta)
    ubicacion_match = _UBICACION_RE.findall(respuesta)
    respuesta_limpia = _UBICACION_RESTO_RE.sub("", _UBICACION_RE.sub("", _IMAGEN_RE.sub("", respuesta))).strip()

    if imagen_match:
        tg_send_photo(chat_id, imagen_match.group(1))
    for sucursal in ubicacion_match:
        tg_send_location(chat_id, sucursal)

    partes = [p.strip() for p in respuesta_limpia.split("|||") if p.strip()]

    for i, parte in enumerate(partes):
        if i > 0:
            time.sleep(random.uniform(1.5, 2.5))
            tg_send_typing(chat_id)
            time.sleep(random.uniform(1.5, 3.0))
        tg_send_message(chat_id, parte)

    historial.append({"role": "user",      "content": text})
    historial.append({"role": "assistant", "content": respuesta_limpia})
    guardar_historial(session_id, historial, canal="telegram", conversation_id=conversation_id,
                      modelo=MODELO_LLM, temperatura=TEMPERATURA, prompt_version=PROMPT_VERSION,
                      confianza=meta_tg.get("confianza"), contexto=meta_tg.get("contexto"),
                      memoria=meta_tg.get("memoria"),
                      logica_negocio=",".join(meta_tg.get("logica_negocio") or []) or None)


@app.route("/setup/telegram")
def setup_telegram():
    ngrok_url = request.args.get("url", "").rstrip("/")
    if not ngrok_url:
        return jsonify({"error": "Pasá ?url=https://tu-ngrok-url"}), 400
    res = http.post(f"{TELEGRAM_API}/setWebhook",
                    json={"url": f"{ngrok_url}/webhook/telegram"})
    return jsonify(res.json())


# ── WhatsApp helpers ──────────────────────────────────────────

# Errores transitorios de WA que vale la pena reintentar
_WA_ERRORES_TRANSITORIOS = {130429, 131000}
_MAX_REINTENTOS_WA = 3

# message_id -> {to, text, intentos, timestamp}
_wa_pendientes: dict[str, dict] = {}
_wa_pendientes_lock = threading.Lock()


def wa_send_message(to: str, text: str) -> str | None:
    """Envía mensaje WA y registra el message_id para tracking de fallos. Retorna el message_id."""
    try:
        res = http.post(WA_API,
                  headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
                  json={
                      "messaging_product": "whatsapp",
                      "to": to,
                      "type": "text",
                      "text": {"body": text},
                  }, timeout=10)
        msg_id = res.json().get("messages", [{}])[0].get("id")
        if msg_id:
            with _wa_pendientes_lock:
                _wa_pendientes[msg_id] = {"to": to, "text": text, "intentos": 1}
        return msg_id
    except Exception as e:
        logger.error(f"Error enviando mensaje WhatsApp: {e}")
        return None


def _wa_reintentar(msg_id: str):
    with _wa_pendientes_lock:
        info = _wa_pendientes.get(msg_id)
        if not info:
            return
        if info["intentos"] >= _MAX_REINTENTOS_WA:
            logger.error(f"WA mensaje {msg_id} falló tras {_MAX_REINTENTOS_WA} intentos para {info['to']}")
            del _wa_pendientes[msg_id]
            return
        info["intentos"] += 1

    logger.info(f"Reintentando mensaje WA {msg_id} (intento {info['intentos']})")
    try:
        res = http.post(WA_API,
                  headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
                  json={
                      "messaging_product": "whatsapp",
                      "to": info["to"],
                      "type": "text",
                      "text": {"body": info["text"]},
                  }, timeout=10)
        new_id = res.json().get("messages", [{}])[0].get("id")
        with _wa_pendientes_lock:
            del _wa_pendientes[msg_id]
            if new_id:
                _wa_pendientes[new_id] = {"to": info["to"], "text": info["text"], "intentos": info["intentos"]}
    except Exception as e:
        logger.error(f"Error en reintento WA {msg_id}: {e}")


def wa_send_typing(to: str):
    pass  # WhatsApp Cloud API no soporta typing indicator por ahora


def wa_send_photo(to: str, modelo: str):
    path = IMAGENES_MODELOS.get(modelo.lower())
    if not path or not os.path.exists(path):
        logger.warning(f"Imagen no encontrada para modelo: {modelo}")
        return
    try:
        with open(path, "rb") as f:
            upload = http.post(
                f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/media",
                headers={"Authorization": f"Bearer {WA_TOKEN}"},
                files={"file": (os.path.basename(path), f, "image/webp")},
                data={"messaging_product": "whatsapp"},
                timeout=20,
            )
        media_id = upload.json().get("id")
        if not media_id:
            logger.error(f"No se obtuvo media_id: {upload.text}")
            return
        http.post(WA_API,
                  headers={"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"},
                  json={
                      "messaging_product": "whatsapp",
                      "to": to,
                      "type": "image",
                      "image": {"id": media_id},
                  }, timeout=10)
    except Exception as e:
        logger.error(f"Error enviando imagen WhatsApp: {e}")


@app.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_webhook():
    data = request.get_json(silent=True) or {}
    try:
        entry   = data["entry"][0]
        changes = entry["changes"][0]["value"]
    except (KeyError, IndexError):
        return "", 200

    # Manejar status updates (delivered, failed, etc.)
    for status in changes.get("statuses", []):
        msg_id     = status.get("id")
        status_val = status.get("status")
        if status_val == "delivered":
            with _wa_pendientes_lock:
                _wa_pendientes.pop(msg_id, None)
        elif status_val == "failed":
            error_code = status.get("errors", [{}])[0].get("code", 0)
            logger.warning(f"WA mensaje {msg_id} falló con código {error_code}")
            if error_code in _WA_ERRORES_TRANSITORIOS:
                threading.Thread(target=_wa_reintentar, args=(msg_id,), daemon=True).start()
            else:
                with _wa_pendientes_lock:
                    _wa_pendientes.pop(msg_id, None)

    try:
        message = changes["messages"][0]
    except (KeyError, IndexError):
        return "", 200

    from_number = message["from"]
    msg_type    = message.get("type")

    if msg_type == "text":
        text = message["text"]["body"].strip()
    elif msg_type == "audio":
        audio_id = message["audio"]["id"]
        try:
            media_url = http.get(
                f"https://graph.facebook.com/v19.0/{audio_id}",
                headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=10
            ).json().get("url")
            audio_bytes = http.get(
                media_url,
                headers={"Authorization": f"Bearer {WA_TOKEN}"}, timeout=30
            ).content
        except Exception as e:
            logger.error(f"Error descargando audio WhatsApp: {e}")
            wa_send_message(from_number, "No se escucha bien el audio. Me lo mandás de nuevo o me escribís?")
            return "", 200
        text = transcribir_audio(audio_bytes, MODELO_LLM) or ""
        if not text:
            wa_send_message(from_number, "No se escucha bien el audio. Me lo mandás de nuevo o me escribís?")
            return "", 200
        logger.info(f"Audio WA transcripto [{from_number}]: {text}")
    else:
        return "", 200

    if not text or text.startswith("/"):
        return "", 200

    session_id = f"wa_{from_number}"
    _buffer_message(session_id, text, lambda t: _procesar_wa(from_number, session_id, t))
    return "", 200


def _procesar_wa(from_number: str, session_id: str, text: str):
    historial       = obtener_historial(session_id)
    conversation_id = obtener_conversation_id(session_id)
    agente          = obtener_o_asignar_agente(session_id)

    respuesta = ""
    meta_wa = {}
    for intento in range(4):
        try:
            chunks    = list(procesar_mensaje(text, historial, session_id, MODELO_LLM, agente, meta=meta_wa))
            respuesta = limpiar_respuesta("".join(chunks))
            break
        except Exception as e:
            logger.warning(f"Error LLM WhatsApp (intento {intento + 1}/4): {e}")
            if intento == 3:
                wa_send_message(from_number, "Perdoná, tuve un problema. Intentá de nuevo en un momento.")
                return
            time.sleep(60)

    if not respuesta:
        return

    imagen_match     = _IMAGEN_RE.search(respuesta)
    respuesta_limpia = _UBICACION_RE.sub("", _IMAGEN_RE.sub("", respuesta)).strip()

    if imagen_match:
        wa_send_photo(from_number, imagen_match.group(1))

    partes = [p.strip() for p in respuesta_limpia.split("|||") if p.strip()]
    for i, parte in enumerate(partes):
        if i > 0:
            time.sleep(random.uniform(1.5, 2.5))
        wa_send_message(from_number, parte)

    historial.append({"role": "user",      "content": text})
    historial.append({"role": "assistant", "content": respuesta_limpia})
    guardar_historial(session_id, historial, canal="whatsapp", conversation_id=conversation_id,
                      modelo=MODELO_LLM, temperatura=TEMPERATURA, prompt_version=PROMPT_VERSION,
                      confianza=meta_wa.get("confianza"), contexto=meta_wa.get("contexto"),
                      memoria=meta_wa.get("memoria"),
                      logica_negocio=",".join(meta_wa.get("logica_negocio") or []) or None)


# ── Twilio helpers ────────────────────────────────────────────

def twilio_send_message(to: str, text: str):
    try:
        res = http.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={"From": TWILIO_NUMBER, "To": to, "Body": text},
            timeout=10,
        )
        logger.info(f"Twilio send [{res.status_code}] to={to} from={TWILIO_NUMBER}: {res.text[:200]}")
    except Exception as e:
        logger.error(f"Error enviando mensaje Twilio: {e}")


def twilio_send_location(to: str, sucursal: str):
    loc = UBICACIONES.get(sucursal.lower())
    if not loc:
        logger.warning(f"Sucursal no encontrada: {sucursal}")
        return
    url = loc.get("maps_url") or f"https://maps.google.com/?q={loc['lat']},{loc['lng']}"
    twilio_send_message(to, f"{loc['nombre']}\n{url}")


def twilio_send_photo(to: str, modelo: str):
    if not NGROK_URL:
        logger.warning("NGROK_URL no configurada, no se puede enviar imagen por Twilio")
        return
    nombre = f"{modelo.lower()}.jpg"
    media_url = f"{NGROK_URL}/imagenes/{nombre}"
    try:
        res = http.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
            auth=(TWILIO_SID, TWILIO_TOKEN),
            data={"From": TWILIO_NUMBER, "To": to, "MediaUrl": media_url, "Body": ""},
            timeout=10,
        )
        logger.info(f"Twilio foto [{res.status_code}] {media_url}: {res.text[:200]}")
    except Exception as e:
        logger.error(f"Error enviando imagen Twilio: {e}")


@app.route("/webhook/twilio", methods=["POST"])
def twilio_webhook():
    msg_sid = request.form.get("MessageSid", "")
    if msg_sid and _ya_procesado(f"twilio_{msg_sid}"):
        return "", 200

    from_number = request.form.get("From", "")
    msg_type    = request.form.get("MediaContentType0", "")
    text        = request.form.get("Body", "").strip()

    if msg_type.startswith("audio/"):
        media_url = request.form.get("MediaUrl0", "")
        try:
            audio_bytes = http.get(media_url, auth=(TWILIO_SID, TWILIO_TOKEN), timeout=30).content
        except Exception as e:
            logger.error(f"Error descargando audio Twilio: {e}")
            twilio_send_message(from_number, "No se escucha bien el audio. Me lo mandás de nuevo o me escribís?")
            return "", 200
        text = transcribir_audio(audio_bytes, MODELO_LLM) or ""
        if not text:
            twilio_send_message(from_number, "No se escucha bien el audio. Me lo mandás de nuevo o me escribís?")
            return "", 200
        logger.info(f"Audio Twilio transcripto [{from_number}]: {text}")

    if not text:
        return "", 200

    session_id = f"twilio_{from_number}"
    _buffer_message(session_id, text, lambda t: _procesar_twilio(from_number, session_id, t))
    return "", 200


def _procesar_twilio(from_number: str, session_id: str, text: str):
    historial       = obtener_historial(session_id)
    conversation_id = obtener_conversation_id(session_id)
    agente          = obtener_o_asignar_agente(session_id)

    respuesta = ""
    meta_twilio = {}
    for intento in range(4):
        try:
            chunks    = list(procesar_mensaje(text, historial, session_id, MODELO_LLM, agente, meta=meta_twilio))
            respuesta = limpiar_respuesta("".join(chunks))
            break
        except Exception as e:
            logger.warning(f"Error LLM Twilio (intento {intento + 1}/4): {e}")
            if intento == 3:
                twilio_send_message(from_number, "Perdoná, tuve un problema. Intentá de nuevo en un momento.")
                return
            time.sleep(60)

    if not respuesta:
        return

    logger.info(f"Respuesta agente Twilio [{from_number}]: {respuesta[:300]}")

    imagen_match    = _IMAGEN_RE.search(respuesta)
    ubicacion_match = _UBICACION_RE.findall(respuesta)
    logger.info(f"Tags Twilio — imagen: {imagen_match}, ubicaciones: {ubicacion_match}")
    respuesta_limpia = _UBICACION_RESTO_RE.sub("", _UBICACION_RE.sub("", _IMAGEN_RE.sub("", respuesta))).strip()

    if imagen_match:
        twilio_send_photo(from_number, imagen_match.group(1))
    for sucursal in ubicacion_match:
        twilio_send_location(from_number, sucursal)

    partes = [p.strip() for p in respuesta_limpia.split("|||") if p.strip()]
    for i, parte in enumerate(partes):
        if i > 0:
            time.sleep(random.uniform(1.5, 2.5))
        twilio_send_message(from_number, parte)

    historial.append({"role": "user",      "content": text})
    historial.append({"role": "assistant", "content": respuesta_limpia})
    guardar_historial(session_id, historial, canal="whatsapp", conversation_id=conversation_id,
                      modelo=MODELO_LLM, temperatura=TEMPERATURA, prompt_version=PROMPT_VERSION,
                      confianza=meta_twilio.get("confianza"), contexto=meta_twilio.get("contexto"),
                      memoria=meta_twilio.get("memoria"),
                      logica_negocio=",".join(meta_twilio.get("logica_negocio") or []) or None)


# ── Dashboard ────────────────────────────────────────────────



@app.route("/api/dashboard/metricas")
def _msg_count(mensajes_json: str) -> int:
    try:
        return len(json.loads(mensajes_json or "[]"))
    except Exception:
        return 0


def _metricas_data() -> dict:
    with sqlite3.connect(DB_PATH) as conn:
        hoy = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM ventas WHERE DATE(fecha) = DATE('now', 'localtime')
        """).fetchone()
        semana = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM ventas WHERE fecha >= DATE('now', 'localtime', '-7 days')
        """).fetchone()
        mes = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM ventas
            WHERE fecha >= date('now', 'localtime', 'start of month')
        """).fetchone()
        agentes_activos = conn.execute("""
            SELECT agente, COUNT(*) as chats
            FROM historiales
            WHERE actualizado >= datetime('now', 'localtime', '-2 hours')
              AND agente IS NOT NULL
            GROUP BY agente ORDER BY chats DESC
        """).fetchall()
        chats_activos = conn.execute("""
            SELECT COUNT(*) FROM historiales
            WHERE actualizado >= datetime('now', 'localtime', '-2 hours')
        """).fetchone()[0]
    return {
        "presupuestos_hoy":    hoy[0],
        "total_hoy":           hoy[1],
        "presupuestos_semana": semana[0],
        "total_semana":        semana[1],
        "presupuestos_mes":    mes[0],
        "total_mes":           mes[1],
        "chats_activos":       chats_activos,
        "por_agente":          [{"agente": r[0], "chats": r[1]} for r in agentes_activos],
    }


def _chats_data() -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT session_id, agente, canal, actualizado, mensajes, debug
            FROM historiales
            WHERE actualizado >= datetime('now', 'localtime', '-2 hours')
            ORDER BY actualizado DESC LIMIT 50
        """).fetchall()
    return [{
        "session_id":  r[0],
        "agente":      r[1] or "—",
        "canal":       r[2] or "web",
        "actualizado": r[3],
        "mensajes":    _msg_count(r[4]),
        "debug":       bool(r[5]),
    } for r in rows]


def _logs_data() -> list:
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT conversation_id, session_id, agente, canal, actualizado, mensajes,
                   modelo, temperatura, prompt_version, debug
            FROM conversations
            WHERE actualizado >= datetime('now', 'localtime', '-7 days')
            ORDER BY actualizado DESC LIMIT 200
        """).fetchall()
    return [{
        "conversation_id": r[0],
        "session_id":      r[1],
        "agente":          r[2] or "—",
        "canal":           r[3] or "web",
        "actualizado":     r[4],
        "mensajes":        _msg_count(r[5]),
        "modelo":          r[6] or "—",
        "temperatura":     r[7],
        "prompt_version":  r[8] or "—",
        "debug":           bool(r[9]),
    } for r in rows]


def dashboard_metricas():
    return jsonify(_metricas_data())


@app.route("/api/dashboard/chats")
def dashboard_chats():
    return jsonify({"chats": _chats_data()})


@app.route("/api/dashboard/logs")
def dashboard_logs():
    return jsonify({"logs": _logs_data()})


@app.route("/api/dashboard/chat/<session_id>")
def dashboard_chat_view(session_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT mensajes, agente, canal, actualizado FROM historiales WHERE session_id = ?",
            (session_id,)
        ).fetchone()
    if not row:
        return jsonify({"mensajes": [], "agente": "—", "canal": "web", "actualizado": None})
    try:
        msgs = json.loads(row[0] or "[]")
    except Exception:
        msgs = []
    return jsonify({"mensajes": msgs, "agente": row[1] or "—", "canal": row[2] or "web", "actualizado": row[3]})


@app.route("/api/dashboard/conversation/<conversation_id>")
def dashboard_conversation_view(conversation_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT mensajes, agente, canal, actualizado, modelo, temperatura, prompt_version, debug FROM conversations WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
    if not row:
        return jsonify({"mensajes": [], "agente": "—", "canal": "web", "actualizado": None, "modelo": "—", "temperatura": None, "prompt_version": "—", "debug": False})
    try:
        msgs = json.loads(row[0] or "[]")
    except Exception:
        msgs = []
    return jsonify({
        "mensajes":       msgs,
        "agente":         row[1] or "—",
        "canal":          row[2] or "web",
        "actualizado":    row[3],
        "modelo":         row[4] or "—",
        "temperatura":    row[5],
        "prompt_version": row[6] or "—",
        "debug":          bool(row[7]),
    })


@app.route("/api/debug-session", methods=["GET"])
def debug_session_status():
    return jsonify({"debug": _web_debug_mode})


@app.route("/api/debug-session", methods=["POST"])
def debug_session_toggle():
    global _web_debug_mode
    _web_debug_mode = not _web_debug_mode
    logger.warning(f"Web debug mode: {'ON' if _web_debug_mode else 'OFF'}")
    return jsonify({"debug": _web_debug_mode})


@app.route("/api/dashboard/ventas")
def dashboard_ventas():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT id, agente, marca, modelo, medida, cantidad, total, sucursal, cliente, fecha
            FROM ventas ORDER BY fecha DESC LIMIT 200
        """).fetchall()
    return jsonify({"ventas": [{
        "id":       r[0], "agente": r[1] or "—", "marca": r[2], "modelo": r[3], "medida": r[4],
        "cantidad": r[5], "total":  r[6], "sucursal": r[7] or "—",
        "cliente":  r[8] or "—", "fecha": r[9],
    } for r in rows]})


@app.route("/api/dashboard/stream")
def dashboard_stream():
    def generate():
        while True:
            try:
                payload = {
                    "metricas": _metricas_data(),
                    "chats":    _chats_data(),
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                time.sleep(4)
            except GeneratorExit:
                break
            except Exception as e:
                logger.error(f"SSE error: {e}")
                time.sleep(4)
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.route("/api/dashboard/descargar-ventas")
def dashboard_descargar_ventas():
    import io
    from datetime import datetime as dt
    venta_id = request.args.get("id", type=int)
    with sqlite3.connect(DB_PATH) as conn:
        if venta_id:
            rows = conn.execute("""
                SELECT fecha, agente, marca, modelo, medida, cantidad, total, sucursal, cliente
                FROM ventas WHERE id = ?
            """, (venta_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT fecha, agente, marca, modelo, medida, cantidad, total, sucursal, cliente
                FROM ventas ORDER BY fecha DESC
            """).fetchall()
    buf = io.StringIO()
    sep = "=" * 72
    buf.write(f"PRESUPUESTOS CONFIRMADOS — generado {dt.now().strftime('%d/%m/%Y %H:%M')}\n")
    buf.write(sep + "\n\n")
    for r in rows:
        fecha, agente, marca, modelo, medida, cantidad, total, sucursal, cliente = r
        buf.write(f"Fecha    : {fecha or '—'}\n")
        buf.write(f"Agente   : {agente or '—'}\n")
        buf.write(f"Producto : {marca} {modelo} {medida}\n")
        buf.write(f"Cantidad : {cantidad}\n")
        buf.write(f"Total    : ${total:,.0f}\n")
        buf.write(f"Sucursal : {sucursal or '—'}\n")
        buf.write(f"Cliente  : {cliente or '—'}\n")
        buf.write(sep + "\n\n")
    fecha_arch = dt.now().strftime("%Y%m%d_%H%M")
    sufijo = f"_{venta_id}" if venta_id else f"_{fecha_arch}"
    resp = app.response_class(response=buf.getvalue(), mimetype="text/plain; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="presupuesto{sufijo}.log"'
    return resp


@app.route("/api/dashboard/descargar-logs")
def dashboard_descargar_logs():
    import io
    from datetime import datetime as dt
    conv_filter = request.args.get("conversation")
    with sqlite3.connect(DB_PATH) as conn:
        if conv_filter:
            rows = conn.execute("""
                SELECT conversation_id, agente, canal, actualizado, mensajes,
                       modelo, temperatura, prompt_version, debug,
                       confianza, contexto, memoria, logica_negocio
                FROM conversations WHERE conversation_id = ?
            """, (conv_filter,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT conversation_id, agente, canal, actualizado, mensajes,
                       modelo, temperatura, prompt_version, debug,
                       confianza, contexto, memoria, logica_negocio
                FROM conversations
                WHERE actualizado >= datetime('now', 'localtime', '-7 days')
                ORDER BY actualizado DESC
            """).fetchall()
    buf = io.StringIO()
    sep = "=" * 72
    for r in rows:
        conv_id, agente, canal, actualizado, mensajes_raw, \
            modelo, temperatura, prompt_version, debug, \
            confianza, contexto, memoria, logica_negocio = r
        try:
            msgs = json.loads(mensajes_raw or "[]")
        except Exception:
            msgs = []
        buf.write(sep + "\n")
        buf.write(f"CONVERSACIÓN : {conv_id}\n")
        buf.write(f"AGENTE : {agente or '—'}  |  CANAL: {canal or 'web'}  |  FECHA: {actualizado or '—'}\n")
        debug_str = "  |  DEBUG: SI" if debug else ""
        buf.write(f"MODELO : {modelo or '—'}  |  TEMP: {temperatura if temperatura is not None else '—'}  |  PROMPT: {prompt_version or '—'}{debug_str}\n")
        buf.write(f"CONFIANZA : {confianza or '—'}  |  CONTEXTO: {contexto or '—'} tokens  |  MEMORIA: {memoria if memoria is not None else '—'} msgs\n")
        buf.write(f"LÓGICA    : {logica_negocio or '—'}\n")
        buf.write(sep + "\n")
        for msg in msgs:
            rol       = "Cliente" if msg.get("role") == "user" else (agente or "Agente")
            contenido = msg.get("content", "").strip().replace("\n", "\n         ")
            buf.write(f"  [{rol}]  {contenido}\n\n")
        buf.write("\n")
    fecha  = dt.now().strftime("%Y%m%d_%H%M")
    sufijo = f"_{conv_filter[:8]}" if conv_filter else f"_{fecha}"
    resp   = app.response_class(response=buf.getvalue(), mimetype="text/plain; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="conversacion{sufijo}.log"'
    return resp


@app.route("/api/logs/stream")
def server_logs_stream():
    def generate():
        with _log_lock:
            backlog = list(_log_buffer)[-100:]
        for entry in backlog:
            yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
        last_n = backlog[-1]["n"] if backlog else -1
        while True:
            try:
                time.sleep(0.5)
                with _log_lock:
                    snapshot = list(_log_buffer)
                new = [e for e in snapshot if e["n"] > last_n]
                for entry in new:
                    yield f"data: {json.dumps(entry, ensure_ascii=False)}\n\n"
                if new:
                    last_n = new[-1]["n"]
            except GeneratorExit:
                break
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


if __name__ == "__main__":
    _init_db()
    print("=" * 60)
    print("  Neumáticos Martinez - API Backend (Flask)")
    print("=" * 60)

    disponible, mensaje = verificar_gemini(MODELO_LLM)
    if disponible:
        print(f"  OK: {mensaje}")
    else:
        print(f"  AVISO: {mensaje}")

    print(f"\n  API escuchando en: http://localhost:5000")
    print("  Inicia el frontend con: node server.js")
    print("=" * 60 + "\n")

    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
