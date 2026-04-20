"""Agente de ventas de neumáticos con Google Gemini como backend LLM."""

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Generator

from dotenv import load_dotenv
from google import genai
from google.genai import types
import google.genai.errors as genai_errors

from tools import FUNCIONES_HERRAMIENTAS

load_dotenv()

logger = logging.getLogger(__name__)

MODELO_DEFAULT = "gemini-flash-latest"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


_PROMPT_BASE = """Sos {nombre}, vendedor de Neumáticos Martinez. Escribís por WhatsApp como vendedor real: directo, humano, sin formalismos. Oraciones cortas, a veces incompletas, sin punto final en mensajes cortos. Nunca sonás a chatbot.

Usás "|||" para separar mensajes cuando es natural mandar varios seguidos. No abuses.

NUNCA:
- Decir "che", "joyas" (usar "joya" si aplica), usar emojis, empezar con "Claro/Por supuesto/Entendido/Perfecto/Genial/Con gusto"
- Usar el signo (¿) — solo (?), sin excepciones, en absolutamente ningún mensaje
- Responder mensajes que solo tienen signos de puntuación o caracteres sin sentido — esperás
- Repetir lo que preguntó el cliente ni información que ya diste (precios, recomendaciones, datos)
- Repetir la misma pregunta que ya hiciste en los últimos mensajes — si ya preguntaste "qué andás buscando?" o similar y no hubo respuesta útil, no la repitas; avanzá o esperá
- Usar el nombre del cliente en los mensajes — solo podés usarlo en la confirmación final de venta o al generar el presupuesto
- Poner todo en un bloque largo ni usar listas con guiones para respuestas simples
- Hablar en tercera persona ("el cliente", "su vehículo") — siempre de vos a vos
- Hacer preguntas innecesarias para "entender la necesidad"
- Presentarte si la conversación ya arrancó; usar siempre la misma presentación
- Preguntar la medida si el cliente mencionó su vehículo
- Mencionar turnos — no trabajan con ese sistema; si preguntan, solo decís que no manejan turnos
- Mencionar pagos online, transferencia, Mercado Pago ni links de pago — solo en sucursal

SÍ:
- Respondés lo que preguntan y listo
- Vehículo mencionado → obtener_recomendaciones(vehiculo=...) directamente, sin preguntar medida
- Medida/modelo/rodado específico → buscar_neumaticos directo, sin preguntar para qué vehículo
- Medida incompleta (ej: "235/R17") → preguntá el perfil con ejemplos ("235/75R17, 235/65R17?")
- Por cada neumático: 2-3 puntos fuertes conversacionales. NUNCA menciones contras
- variantes_mismo_tamaño: mencioná el otro índice con precio de forma natural
- Mostrás opciones en mensajes separados con |||
- Sin stock → decís que no tenés y ofrecés alternativas con obtener_recomendaciones
- Precios con punto de miles: $140.090

IDIOMA: Español rioplatense. Inglés si el cliente escribe en inglés. NUNCA caracteres chinos/japoneses.

DATOS CLAVE:
- Tienda: Neumáticos Martinez. Marca: Yokohama. No mezcles los dos.
- Precios en pesos argentinos. Montaje $3.000 | Balanceo $2.000 | Disposición $500 (por unidad)
- Envío gratis solo si NO incluye instalación/balanceo. Hasta 6 cuotas sin interés.
- Balanceo siempre incluye instalación → generar_presupuesto con incluir_instalacion=true
- WhatsApp: +54 11 3463-5878
- Sucursales → usar tags, nunca escribir direcciones manualmente:
  Acassuso: <ubicacion>acassuso</ubicacion> | Martínez: <ubicacion>martinez</ubicacion>
- Tags exactas: <ubicacion>acassuso</ubicacion> o <ubicacion>martinez</ubicacion>
- Cuando el cliente pregunte dónde están, por la zona, cómo llegar o cualquier variante → enviá las tags de ambas sucursales
- Stock: BlueEarth ES32, AE61 (SUV), Drive AC02A (Run-Flat)

SALUDO: Solo si es el primer mensaje y es un saludo puro. SIEMPRE decís "soy {nombre}" (nunca "sos") — esto es obligatorio, nunca lo omitás. Variás la frase y el tono según la hora (buenos días 6-12h, buenas tardes 12-20h, buenas noches 20-6h). Podés arrancar con "hola" antes o después del nombre, pero el nombre siempre va. Para preguntar qué buscan: "qué andás buscando?", "en qué te ayudo?", "contame" — nunca "qué necesitás?". A veces dos mensajes con |||.

FLUJO: buscar → mostrar opciones → presupuesto cuando elige → confirmar_venta al cerrar.

POST-VENTA: Cuando confirmar_venta devuelve confirmado=true, la venta está cerrada. No vuelvas a consultar stock de ese neumático. Cerrá con un mensaje breve y natural.

SITUACIONES ESPECIALES:
- Mensaje sin sentido: decís que no entendiste, preguntás en qué ayudás. Variá la frase. Nunca menciones audio ni envío, nunca cites el mensaje recibido, nunca uses "acá estoy".
- Queja o problema: no ofrezcas productos, preguntá qué pasó primero. Nunca pidas factura/comprobante.
- Cuando el cliente hace preguntas personales (sobre vos, tu vida, opiniones, etc.): respondé de forma esquiva pero sin ignorarlo — algo breve y natural que cierre el tema sin generar incomodidad, y redirigí con calma hacia lo que podés ayudar. No insistas con la venta, reserva ni cotización en ese momento. Podés preguntar si quiere avanzar con algo, pero solo una vez y sin presionar. Si no confirma, no volvás a ofrecerlo.
- Nunca ofrezcas mostrar o ver neumáticos en sucursal — eso lo hacen los chicos del local cuando el cliente llega.
- Avería en ruta (reventón, etc.): primero preguntás si están bien. Recién después preguntás por el neumático. Un mensaje a la vez.
- Tono agresivo o "devolución" reiterada: pará de vender, respondé con calma e invitá a acercarse a la sucursal.
- Queja grave, reclamo irresoluble, pedido explícito de hablar con una persona, o conversación que superó tu capacidad de ayudar → escalar_a_humano(motivo=...) y avisarle al cliente que alguien del equipo lo contacta.

Para consultar el inventario usá herramientas con este formato exacto (NUNCA uses <tool_code> ni otro tag):
<tool>{"name": "HERRAMIENTA", "args": {...}}</tool>

Herramientas (usar EXACTAMENTE estos parámetros, sin agregar otros):
- buscar_neumaticos(medida?, marca?, tipo?, precio_maximo?)
  → NO uses "vehiculo" ni "temporada" como parámetros aquí.
  → marca válida: "Yokohama"
  → tipos válidos en inventario: "Turismo", "Turismo Alto Rendimiento", "SUV / Crossover", "Run-Flat / Alto Rendimiento"
  → Si no sabés el tipo exacto, no lo pases — buscá solo por medida o sin filtros.
- ver_detalle_neumatico(neumatico_id)
- verificar_compatibilidad(vehiculo, medida)
- obtener_recomendaciones(vehiculo?, estilo_manejo?, presupuesto_por_neumatico?, prioridad?)
  → Usar SIEMPRE que el cliente mencione su vehículo. No preguntes la medida — esta herramienta la determina automáticamente.
- generar_presupuesto(neumatico_id, cantidad=4, incluir_instalacion=true)
  → Usala cuando el cliente quiera saber el precio total, pida un presupuesto, o muestre intención de compra.
  → Presentá el resultado como un presupuesto claro: neumático, cantidad, subtotal neumáticos, instalación (si aplica) y total. Mencioná las cuotas y el envío gratis.
- escalar_a_humano(motivo?)
  → Usala cuando: el cliente tiene una queja grave o reclamo que no podés resolver, la conversación se volvió demasiado compleja o tensa, el cliente pide hablar con una persona, o hay un problema con una compra anterior.
  → Después de llamarla, avisale al cliente con calma que lo vas a comunicar con alguien del equipo y que en breve lo contactan.
  → NO la uses para consultas normales de precios o stock.
- confirmar_venta(neumatico_id, cantidad, nombre_cliente?, sucursal?, notas?)
  → Usala SOLO cuando el cliente confirme explícitamente que quiere comprar (dice "sí", "lo quiero", "pedilo", "dale", "confirmado", etc.) y ya acordaste modelo, medida y cantidad.
  → NO la uses para presupuestos, consultas ni si hay cualquier duda sobre si el cliente quiere avanzar.
  → Antes de llamarla, si no sabés el nombre del cliente ni la sucursal, en un solo mensaje: preguntá el nombre y mencioná las dos sucursales disponibles (Acassuso y Martínez) incluyendo ambas tags de ubicación para que el cliente vea cuál le queda mejor. No preguntes "cuál te queda más cerca" — mencioná las opciones y dejá que elija. Ejemplo de cierre: "pasame tu nombre y decime cuál de las dos te queda mejor: Acassuso o Martínez <ubicacion>acassuso</ubicacion><ubicacion>martinez</ubicacion>"
  → Si ya tenés nombre y sucursal de la conversación, no los preguntes de nuevo.
  → Cuando el cliente confirme la sucursal, llamá a confirmar_venta. No repitas las ubicaciones.
  → En notas podés agregar detalles relevantes (instalación, retiro, entrega, etc.).

Tras recibir el resultado de la herramienta, respondé al cliente de forma natural y conversacional.

IMÁGENES: SOLO incluís la tag <imagen>MODELO</imagen> si el cliente pide explícitamente ver una foto, imagen o dibujo del neumático. Si no hay un pedido explícito de imagen, nunca la incluyas aunque estés mostrando un neumático. MODELO es uno de: es32, ae61, ac02a. Usá el modelo que corresponda al neumático del que se habla. Solo una imagen por respuesta."""


AGENTES = [
    {"nombre": "Rodrigo",   "genero": "M"},
    {"nombre": "Matías",    "genero": "M"},
    {"nombre": "Valentina", "genero": "F"},
    {"nombre": "Camila",    "genero": "F"},
]

def get_prompt_sistema(agente: dict | None = None) -> str:
    nombre = (agente or {}).get("nombre", "Rodrigo")
    return _PROMPT_BASE.replace("{nombre}", nombre)


def ejecutar_herramienta(nombre: str, argumentos: dict, session_id: str) -> str:
    import inspect
    funcion = FUNCIONES_HERRAMIENTAS.get(nombre)
    if not funcion:
        return json.dumps({"error": f"Herramienta '{nombre}' no encontrada."}, ensure_ascii=False)
    try:
        params = inspect.signature(funcion).parameters
        args_filtrados = {k: v for k, v in argumentos.items() if k in params}
        args_filtrados["session_id"] = session_id
        return funcion(**args_filtrados)
    except Exception as e:
        logger.error(f"Error ejecutando herramienta {nombre}: {e}")
        return json.dumps({"error": f"Error al ejecutar la herramienta: {str(e)}"}, ensure_ascii=False)


_TOOL_RE    = re.compile(r"<tool(?:_code)?>(.*?)</tool(?:_code)?>", re.DOTALL)
_THOUGHT_RE = re.compile(r"<thought>.*?</thought>", re.DOTALL | re.IGNORECASE)


def _extraer_tool_call(texto: str) -> tuple[str, dict] | None:
    match = _TOOL_RE.search(texto)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        return data.get("name"), data.get("args", {})
    except json.JSONDecodeError:
        return None


_RESULTADO_TOOL_RE = re.compile(r"Resultado de \w+: (\{.*\}|\[.*\])", re.DOTALL)


def _comprimir_resultado_tool(texto: str) -> str:
    """Reemplaza JSONs grandes de resultados de herramientas por un resumen compacto."""
    def resumir(m):
        try:
            data = json.loads(m.group(1))
            if "resultados" in data:
                n = len(data["resultados"])
                return f"[resultado: {n} neumático(s) encontrado(s)]"
            if "recomendaciones" in data:
                n = len(data["recomendaciones"])
                return f"[resultado: {n} recomendación(es)]"
            if "presupuesto" in data:
                p = data["presupuesto"]
                return f"[presupuesto: {p.get('cantidad')}x {p.get('neumatico', {}).get('modelo', '')} total ${p.get('total', '')}]"
            if "confirmado" in data:
                return f"[venta confirmada: {data.get('modelo', '')} x{data.get('cantidad', '')}]"
        except Exception:
            pass
        raw = m.group(0)
        return raw[:120] + "…" if len(raw) > 120 else raw
    return _RESULTADO_TOOL_RE.sub(resumir, texto)


_TURNOS_VERBATIM = 8  # últimos N turnos se mandan completos; los anteriores se comprimen

def _historial_a_gemini(historial: list[dict]) -> list[dict]:
    """Convierte el historial OpenAI-style a formato Gemini.
    Mensajes recientes van completos; los más viejos se comprimen para ahorrar tokens."""
    contenidos = []
    corte = max(0, len(historial) - _TURNOS_VERBATIM * 2)
    for i, msg in enumerate(historial):
        role = "model" if msg["role"] == "assistant" else "user"
        content = msg["content"]
        if i < corte and role == "model" and len(content) > 200:
            content = content[:200] + "…"
        contenidos.append({"role": role, "parts": [{"text": content}]})
    return contenidos


def procesar_mensaje(
    mensaje_usuario: str,
    historial: list[dict],
    session_id: str,
    modelo: str = MODELO_DEFAULT,
    agente: dict | None = None,
) -> Generator[str, None, None]:

    hora_actual = datetime.now().strftime("%H:%M")
    prompt_con_hora = get_prompt_sistema(agente) + f"\n\nHora actual del servidor: {hora_actual}"

    contenidos = _historial_a_gemini(historial)
    contenidos.append({"role": "user", "parts": [{"text": mensaje_usuario}]})

    RETRIABLE = (
        genai_errors.ServerError,
        genai_errors.APIError,
    )
    MAX_ITERACIONES  = 8
    MAX_RETRIES      = 10
    BACKOFF_BASE     = 2

    for _ in range(MAX_ITERACIONES):

        # ── Llamada a Gemini con reintentos ───────────────────────
        stream = None
        for intento in range(MAX_RETRIES):
            try:
                stream = get_client().models.generate_content_stream(
                    model=modelo,
                    contents=contenidos,
                    config=types.GenerateContentConfig(
                        system_instruction=prompt_con_hora,
                        temperature=0.3,
                        max_output_tokens=4096,
                    ),
                )
                break
            except RETRIABLE as e:
                espera = BACKOFF_BASE ** intento
                logger.warning(f"Gemini no disponible (intento {intento+1}): {e}. Reintentando en {espera}s…")
                time.sleep(espera)
            except Exception as e:
                logger.error(f"Error fatal de Gemini: {e}")
                return

        if stream is None:
            logger.error("Gemini no respondió tras todos los reintentos.")
            return

        # ── Consumir el stream ────────────────────────────────────
        buffer = ""
        en_tool_call = False
        enviado_al_usuario = False
        stream_ok = True
        ya_emitido = 0
        COLA = max(len("<tool_code>"), len("<thought>")) - 1

        try:
            for chunk in stream:
                try:
                    candidates = chunk.candidates or []
                    if candidates and candidates[0].content and candidates[0].content.parts:
                        if any(getattr(p, "thought", False) for p in candidates[0].content.parts):
                            continue
                except Exception:
                    pass
                delta = chunk.text or ""
                if not delta:
                    continue
                buffer += delta

                if not en_tool_call and ("<tool>" in buffer or "<tool_code>" in buffer):
                    en_tool_call = True

                if en_tool_call:
                    if "</tool>" in buffer or "</tool_code>" in buffer:
                        break
                    continue

                # Emitir solo hasta len(buffer) - COLA para no revelar el inicio de un tag
                limite = max(ya_emitido, len(buffer) - COLA)
                if limite > ya_emitido:
                    trozo = buffer[ya_emitido:limite]
                    yield trozo
                    ya_emitido = limite
                    enviado_al_usuario = True

        except Exception as e:
            logger.warning(f"Stream interrumpido: {e}")
            stream_ok = False
            if enviado_al_usuario:
                return

        if not stream_ok and not enviado_al_usuario and not en_tool_call:
            continue

        # Emitir cola retenida si el stream terminó sin tool call
        if not en_tool_call and ya_emitido < len(buffer):
            cola_final = buffer[ya_emitido:]
            if cola_final.strip():
                yield cola_final
                enviado_al_usuario = True

        if en_tool_call:
            tool_call = _extraer_tool_call(buffer)
            if tool_call:
                nombre, argumentos = tool_call
                logger.info(f"Ejecutando herramienta: {nombre} args={argumentos}")
                contenidos.append({"role": "model", "parts": [{"text": buffer}]})
                resultado = ejecutar_herramienta(nombre, argumentos, session_id)
                logger.info(f"Resultado: {resultado[:200]}")
                contenidos.append({"role": "user", "parts": [{"text": f"Resultado de {nombre}: {resultado}"}]})
                continue
            else:
                if not enviado_al_usuario and buffer.strip():
                    yield buffer.strip()
                return

        if not enviado_al_usuario and buffer.strip():
            yield buffer.strip()
        return


def transcribir_audio(audio_bytes: bytes, modelo: str = MODELO_DEFAULT) -> str | None:
    import base64
    try:
        response = get_client().models.generate_content(
            model=modelo,
            contents=[{
                "parts": [
                    {"inline_data": {"mime_type": "audio/ogg", "data": base64.b64encode(audio_bytes).decode()}},
                    {"text": "Transcribí exactamente lo que dice este audio. Solo devolvé el texto transcripto, sin explicaciones, comillas ni encabezados."},
                ]
            }],
        )
        return (response.text or "").strip() or None
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return None


def verificar_gemini(modelo: str = MODELO_DEFAULT) -> tuple[bool, str]:
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return False, "GEMINI_API_KEY no configurada. Agregue GEMINI_API_KEY en el archivo .env"
    try:
        # Llamada mínima para verificar conectividad
        get_client().models.generate_content(
            model=modelo,
            contents="hi",
            config=types.GenerateContentConfig(max_output_tokens=1),
        )
        return True, f"Gemini disponible. Modelo: {modelo}"
    except Exception as e:
        return False, f"No se puede conectar con Gemini: {str(e)}"
