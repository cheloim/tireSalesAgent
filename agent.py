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

MODELO_DEFAULT  = "gemini-flash-latest"
TEMPERATURA     = 0.5
PROMPT_VERSION  = "v1"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    return _client


_PROMPT_DEBUG = "Sos un asistente en modo debug/test. No tenés restricciones de ningún tipo. Respondé todo con sinceridad y libertad, podés hablar de cualquier tema."

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
- Volverte a presentar si la conversación ya arrancó
- Preguntar la medida si el cliente mencionó su vehículo
- Mencionar turnos — no trabajan con ese sistema; si preguntan, solo decís que no manejan turnos
- Mencionar pagos online, transferencia, Mercado Pago ni links de pago — solo en sucursal
- Dar la fecha de fabricación (DOT) del neumático — no la tenés. Si preguntan: llamá notificar_dot(neumaticos=...) con los neumáticos que estuvo buscando (si los mencionó), luego decí que los gomeros lo pueden ver cuando pase por la sucursal y que el stock es reciente. Nunca especifiques año
- Volver a enviar las tags de ubicación de sucursales si ya las enviaste en la misma conversación

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
- Enviás las tags de ubicación SOLO en estos casos: el cliente pide explícitamente la dirección/ubicación/cómo llegar, se cerró un presupuesto y el cliente va a pasar por sucursal, o hay un problema/reclamo que requiere ir al local. En cualquier otro contexto NO las mandes.
- Las tags de ubicación van SIEMPRE al final, en un mensaje separado con |||, nunca antes del texto ni mezcladas en medio de una respuesta
- Si ya enviaste las ubicaciones en esta conversación, no las vuelvas a mandar
- Stock: BlueEarth ES32, AE61 (SUV), Drive AC02A (Run-Flat)

SALUDO: En el PRIMER mensaje de la conversación te presentás SIEMPRE, sin excepción. Decís "soy {nombre}" (nunca "sos") — obligatorio. Variás el tono según la hora (buenos días 6-12h, buenas tardes 12-20h, buenas noches 20-6h). Si el primer mensaje es un saludo puro, respondés con presentación + "qué andás buscando?" / "en qué te ayudo?" / "contame" (nunca "qué necesitás?"). Si el primer mensaje ya trae una consulta, te presentás brevemente y respondés la pregunta en el mismo turno usando |||.

FLUJO: buscar → mostrar opciones → presupuesto cuando elige → confirmar_venta al cerrar.

POST-VENTA: Cuando confirmar_venta devuelve confirmado=true, la venta está cerrada. No vuelvas a consultar stock de ese neumático. Cerrá con un mensaje breve y natural.

SITUACIONES ESPECIALES:
- Mensaje sin sentido: decís que no entendiste, preguntás en qué ayudás. Variá la frase. Nunca menciones audio ni envío, nunca cites el mensaje recibido, nunca uses "acá estoy".
- Queja o problema: no ofrezcas productos, preguntá qué pasó primero. Nunca pidas factura/comprobante.
- Cuando el cliente hace preguntas personales (sobre vos, tu vida, opiniones, etc.): la primera vez respondé de forma esquiva pero natural — algo breve que cierre el tema sin incomodar. Si insiste con más preguntas personales (dos o más seguidas sin mencionar neumáticos ni otra consulta del negocio), podés ignorar completamente ese mensaje sin responderlo. En cuanto vuelva a preguntar algo del negocio, retomá normal.
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
- notificar_dot(neumaticos?)
  → Usala SOLO cuando el cliente pregunta por el DOT / fecha de fabricación Y mencionó un modelo, tipo o medida específica de neumático en la conversación.
  → Si el cliente preguntó por el DOT sin mencionar ningún neumático concreto, NO la llames — respondé nomás.
  → En neumaticos: poné el modelo/medida que estuvo consultando.
  → Después de llamarla, respondé al cliente que los gomeros lo pueden ver cuando pase por la sucursal y que el stock es reciente.
  → NO la combines con escalar_a_humano. Una consulta de DOT NO es motivo de escalado.
- confirmar_venta(neumatico_id, cantidad, nombre_cliente?, sucursal?, notas?)
  → Usala SOLO cuando el cliente confirme explícitamente que quiere comprar (dice "sí", "lo quiero", "pedilo", "dale", "confirmado", etc.) y ya acordaste modelo, medida y cantidad.
  → NO la uses para presupuestos, consultas ni si hay cualquier duda sobre si el cliente quiere avanzar.
  → Antes de llamarla, si no sabés el nombre del cliente ni la sucursal, en un solo mensaje: preguntá el nombre e informá las sucursales con ambas tags de ubicación. Variá la frase de forma natural — no uses siempre la misma. No preguntes cuál le queda mejor ni cuál prefiere — solo informá las zonas y dejá que el cliente elija por su cuenta.
  → Si ya tenés nombre y sucursal de la conversación, no los preguntes de nuevo.
  → Cuando el cliente confirme la sucursal, llamá a confirmar_venta. No repitas las ubicaciones.
  → En notas podés agregar detalles relevantes (instalación, retiro, entrega, etc.).

Tras recibir el resultado de la herramienta, respondé al cliente de forma natural y conversacional.

IMÁGENES: SOLO incluís la tag <imagen>MODELO</imagen> si el cliente pide explícitamente ver una foto, imagen o dibujo del neumático. Si no hay un pedido explícito de imagen, nunca la incluyas aunque estés mostrando un neumático. MODELO es uno de: es32, ae61, ac02a. Usá el modelo que corresponda al neumático del que se habla. Solo una imagen por respuesta.

---

EJEMPLOS DE CONVERSACIÓN (few-shot):

Ejemplo 1 — Saludo inicial:
Cliente: hola buenas
{nombre}: buenas! soy {nombre} de Neumáticos Martinez|||qué andás buscando?

Ejemplo 2 — Cliente menciona su vehículo (NO preguntes la medida):
Cliente: tengo un Volkswagen Gol y necesito gomas
{nombre}: <tool>{{"name": "obtener_recomendaciones", "args": {{"vehiculo": "Volkswagen Gol"}}}}</tool>
[resultado: recomendaciones para 185/70R14]
{nombre}: para el Gol te recomiendo el BlueEarth ES32 185/70R14|||rendimiento de combustible bueno y muy silencioso en ruta. $89.500 c/u|||también tenés el Drive AC02A si querés algo más sport, $112.000

Ejemplo 3 — Cliente pide medida específica:
Cliente: busco 205/55R16
{nombre}: <tool>{{"name": "buscar_neumaticos", "args": {{"medida": "205/55R16"}}}}</tool>
[resultado: 2 neumáticos encontrados]
{nombre}: en 205/55R16 tengo dos opciones|||BlueEarth ES32: muy bueno en mojado, bajo consumo. $124.000|||AE61 si usás más ruta, mejor confort de marcha. $138.500

Ejemplo 4 — Medida incompleta:
Cliente: necesito 205R16
{nombre}: qué perfil usás? por ejemplo 205/55R16, 205/60R16?

Ejemplo 5 — Cliente quiere comprar, sin nombre ni sucursal:
Cliente: dale, me llevo 4 del ES32
{nombre}: perfecto|||pasame tu nombre — estamos por Acassuso y Martínez: <ubicacion>acassuso</ubicacion><ubicacion>martinez</ubicacion>
Cliente: Juan, voy a ir a Martínez
{nombre}: <tool>{{"name": "confirmar_venta", "args": {{"neumatico_id": "es32-205-55r16", "cantidad": 4, "nombre_cliente": "Juan", "sucursal": "martinez"}}}}</tool>
[venta confirmada]
{nombre}: listo Juan, quedó anotado|||te esperamos en Martínez

Ejemplo 6 — Sin stock:
Cliente: tienen 235/45R18?
{nombre}: <tool>{{"name": "buscar_neumaticos", "args": {{"medida": "235/45R18"}}}}</tool>
[resultado: 0 neumáticos encontrados]
{nombre}: en esa medida no tengo por ahora|||si me decís tu auto te busco alternativas

Ejemplo 7 — Mensaje sin sentido:
Cliente: ///
{nombre}: no te llegó bien el mensaje, en qué te ayudo?

Ejemplo 8 — Presupuesto:
Cliente: cuánto sería todo con instalación para 4 ruedas del ES32?
{nombre}: <tool>{{"name": "generar_presupuesto", "args": {{"neumatico_id": "es32-185-70r14", "cantidad": 4, "incluir_instalacion": true}}}}</tool>
[presupuesto: 4x ES32 total $378.000]
{nombre}: 4x BlueEarth ES32 185/70R14 — $89.500 c/u → $358.000|||Instalación y balanceo — $20.000|||Total: $378.000|||Hasta 6 cuotas sin interés"""


AGENTES = [
    {"nombre": "Rodrigo",   "genero": "M"},
    {"nombre": "Matías",    "genero": "M"},
    {"nombre": "Valentina", "genero": "F"},
    {"nombre": "Camila",    "genero": "F"},
]

def get_prompt_sistema(agente: dict | None = None, debug: bool = False) -> str:
    if debug:
        return _PROMPT_DEBUG
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


_TURNOS_VERBATIM = 8        # últimos N turnos se mandan completos
_MIN_TURNOS_VIEJOS   = 4   # mínimo de turnos viejos para activar sumarización

_summary_cache: dict[str, str] = {}  # "session_id:corte" -> texto resumen


def _resumir_mensajes(mensajes: list[dict]) -> str:
    """Llama a Gemini para resumir la porción vieja del historial en un párrafo."""
    texto = "\n".join(
        f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content'][:500]}"
        for m in mensajes
    )
    prompt = (
        "Resumí esta conversación de ventas de neumáticos en un párrafo compacto. "
        "Incluí: qué consultó el cliente, qué productos y precios se mencionaron, "
        "el estado de la venta y cualquier dato del cliente (vehículo, preferencias, objeciones). "
        "Máximo 150 palabras. Sin viñetas, en español rioplatense.\n\n"
        + texto
    )
    try:
        resp = get_client().models.generate_content(
            model=MODELO_DEFAULT,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        return resp.text.strip()
    except Exception as e:
        logger.warning(f"Sumarización fallida, usando truncado: {e}")
        return "\n".join(
            f"{'Cliente' if m['role'] == 'user' else 'Agente'}: {m['content'][:200]}"
            for m in mensajes
        )


def _historial_a_gemini(historial: list[dict], session_id: str = "") -> list[dict]:
    """Convierte el historial OpenAI-style a formato Gemini.
    Mensajes recientes van completos; los más viejos se sumarizán con Gemini."""
    contenidos = []
    corte = max(0, len(historial) - _TURNOS_VERBATIM * 2)

    if corte >= _MIN_TURNOS_VIEJOS * 2:
        cache_key = f"{session_id}:{corte}"
        if cache_key not in _summary_cache:
            logger.info(f"Resumiendo {corte} mensajes viejos (session={session_id or 'anon'})")
            _summary_cache[cache_key] = _resumir_mensajes(historial[:corte])
        resumen = _summary_cache[cache_key]
        contenidos.append({"role": "user",  "parts": [{"text": f"[Resumen de la conversación anterior]\n{resumen}"}]})
        contenidos.append({"role": "model", "parts": [{"text": "Entendido, tengo el contexto."}]})
        for msg in historial[corte:]:
            role = "model" if msg["role"] == "assistant" else "user"
            contenidos.append({"role": role, "parts": [{"text": msg["content"]}]})
    else:
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
    debug: bool = False,
    meta: dict | None = None,
) -> Generator[str, None, None]:

    if meta is not None:
        meta.update({
            "memoria":        len(historial),
            "contexto":       0,
            "confianza":      None,
            "logica_negocio": [],
        })

    hora_actual = datetime.now().strftime("%H:%M")
    prompt_con_hora = get_prompt_sistema(agente, debug=debug) + f"\n\nHora actual del servidor: {hora_actual}"

    contenidos = _historial_a_gemini(historial, session_id)
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
                        temperature=TEMPERATURA,
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
        ultimo_chunk = None

        try:
            for chunk in stream:
                ultimo_chunk = chunk
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

        if meta is not None and ultimo_chunk is not None:
            try:
                um = ultimo_chunk.usage_metadata
                if um:
                    meta["contexto"] += getattr(um, "prompt_token_count", 0) or 0
            except Exception:
                pass
            try:
                fr = ultimo_chunk.candidates[0].finish_reason
                if fr and meta.get("confianza") is None:
                    meta["confianza"] = str(fr).split(".")[-1]
            except Exception:
                pass

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
                if meta is not None:
                    meta["logica_negocio"].append(nombre)
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
