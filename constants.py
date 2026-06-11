# ── Agentes (personas) ─────────────────────────────────────────
AGENTES = ["Rodrigo", "Matías", "Valentina", "Camila"]

# ── Gemini defaults (from agent.py) ──────────────────────────
MODELO_DEFAULT = "gemini-flash-latest"
TEMPERATURA = 0.5
PROMPT_VERSION = "v1"

# ── Timing ────────────────────────────────────────────────────
TYPING_DOT_DELAY = (2, 4)  # segundos antes de "..."
MSG_TYPING_DELAY = (3.0, 9.0)  # segundos por mensaje
MSG_PAUSA_ENTRE = (2, 3)  # segundos entre mensajes
MSG_BUFFER_DELAY = 8  # segundos a esperar antes de procesar buffer

# ── Historial ─────────────────────────────────────────────────
TURNOS_VERBATIM = 8
MIN_TURNOS_VIEJOS = 4
SUMMARY_THRESHOLD_CHARS = 200
SUMMARY_CACHE_MAX = 200

# ── Contexto de retoma ────────────────────────────────────────
GAP_SALUDO_HORAS = 4  # horas a partir de las cuales se saluda de nuevo al retomar conversación

# ── Deduplicación ────────────────────────────────────────────
DEDUP_TTL = 300  # segundos
WA_PENDIENTE_TTL = 3600  # segundos
VENTA_DEDUP_TTL = 86400  # segundos (24h)

# ── Límites ───────────────────────────────────────────────────
MAX_MSG_LENGTH = 4000
MAX_ITERACIONES = 8
MAX_RETRIES = 3
BACKOFF_BASE = 2  # segundos (exponencial)
WA_MAX_REINTENTOS = 3

# ── Colas ─────────────────────────────────────────────────────
COLA_SIZE = 100