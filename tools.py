"""Implementación de herramientas para el agente de ventas de neumáticos."""

import json
import time
from inventory import (
    NEUMATICOS,
    COMPATIBILIDAD_VEHICULOS,
    TARIFA_INSTALACION,
    TARIFA_BALANCEO,
    TARIFA_DESECHO,
    actualizar_stock,
)

def _palabras(texto: str) -> set:
    """Devuelve el conjunto de palabras en minúsculas de un texto."""
    return set(texto.lower().split())


def _coincide(termino: str, campo: str) -> bool:
    """True si alguna palabra del término aparece en el campo (o viceversa)."""
    palabras_termino = _palabras(termino)
    palabras_campo   = _palabras(campo)
    return bool(palabras_termino & palabras_campo)


def buscar_neumaticos(
    medida: str | None = None,
    marca: str | None = None,
    tipo: str | None = None,
    temporada: str | None = None,
    precio_maximo: float | None = None,
    session_id: str = "default",
) -> str:
    resultados = NEUMATICOS[:]

    if medida:
        resultados = [n for n in resultados if medida.upper() in n["medida"].upper()]
    if marca:
        resultados = [n for n in resultados if _coincide(marca, n["marca"])]
    if tipo:
        resultados = [n for n in resultados if _coincide(tipo, n["tipo"])]
    if temporada:
        # Coincidencia flexible: "verano"/"summer" → "todo el año" si no hay match exacto
        strict = [n for n in resultados if _coincide(temporada, n["temporada"])]
        resultados = strict if strict else resultados  # si no coincide, ignorar filtro
    if precio_maximo is not None:
        try:
            resultados = [n for n in resultados if n["precio"] <= float(precio_maximo)]
        except (TypeError, ValueError):
            pass

    if not resultados:
        detalle = []
        if medida:
            detalle.append(f"medida {medida}")
        if marca:
            detalle.append(f"marca {marca}")
        if tipo:
            detalle.append(f"tipo {tipo}")
        criterio = ", ".join(detalle) if detalle else "esos criterios"
        return json.dumps({
            "resultados": [],
            "sin_stock": True,
            "criterio_buscado": criterio,
            "mensaje": f"No hay neumáticos disponibles para {criterio}. Usá obtener_recomendaciones con el vehículo del cliente para ofrecer alternativas.",
        }, ensure_ascii=False)

    salida = []
    for n in resultados:
        salida.append({
            "id": n["id"],
            "marca": n["marca"],
            "modelo": n["modelo"],
            "medida": n["medida"],
            "tipo": n["tipo"],
            "temporada": n["temporada"],
            "precio": n["precio"],
            "stock": n["stock"],
            "garantia_km": n["garantia_km"],
        })
    return json.dumps({"resultados": salida, "total": len(salida)}, ensure_ascii=False)


def ver_detalle_neumatico(neumatico_id: str, session_id: str = "default") -> str:
    neumatico = next((n for n in NEUMATICOS if n["id"] == neumatico_id), None)
    if not neumatico:
        return json.dumps({"error": f"No se encontró el neumático con ID '{neumatico_id}'."}, ensure_ascii=False)
    return json.dumps(neumatico, ensure_ascii=False)


def verificar_compatibilidad(vehiculo: str, medida: str, session_id: str = "default") -> str:
    clave = vehiculo.lower().strip()
    medidas_compatibles = COMPATIBILIDAD_VEHICULOS.get(clave)

    if medidas_compatibles is None:
        for v, medidas in COMPATIBILIDAD_VEHICULOS.items():
            if clave in v or v in clave:
                medidas_compatibles = medidas
                clave = v
                break

    if medidas_compatibles is None:
        vehiculos_disponibles = ", ".join(COMPATIBILIDAD_VEHICULOS.keys())
        return json.dumps({
            "compatible": False,
            "mensaje": f"Vehículo '{vehiculo}' no está en nuestra base de datos. Vehículos disponibles: {vehiculos_disponibles}",
        }, ensure_ascii=False)

    es_compatible = medida.upper() in [m.upper() for m in medidas_compatibles]
    return json.dumps({
        "vehiculo": clave,
        "medida_consultada": medida,
        "compatible": es_compatible,
        "medidas_compatibles": medidas_compatibles,
        "mensaje": (
            f"La medida {medida} {'ES compatible' if es_compatible else 'NO es compatible'} con el {clave}. "
            f"Medidas compatibles: {', '.join(medidas_compatibles)}"
        ),
    }, ensure_ascii=False)


def obtener_recomendaciones(
    vehiculo: str | None = None,
    estilo_manejo: str | None = None,
    presupuesto_por_neumatico: float | None = None,
    prioridad: str | None = None,
    session_id: str = "default",
) -> str:
    """
    estilo_manejo: 'deportivo', 'confort', 'todoterreno', 'economico'
    prioridad: 'rendimiento', 'durabilidad', 'traccion_lluvia', 'nieve', 'precio'
    """
    candidatos = NEUMATICOS[:]

    if vehiculo:
        clave = vehiculo.lower().strip()
        for v, medidas in COMPATIBILIDAD_VEHICULOS.items():
            if clave in v or v in clave:
                candidatos = [n for n in candidatos if n["medida"] in medidas]
                break

    if presupuesto_por_neumatico is not None:
        candidatos = [n for n in candidatos if n["precio"] <= presupuesto_por_neumatico]

    def puntaje(neumatico):
        p = 0
        if estilo_manejo == "deportivo" and "Rendimiento" in neumatico["tipo"]:
            p += 3
        if estilo_manejo == "confort" and "Turismo" in neumatico["tipo"]:
            p += 3
        if estilo_manejo == "todoterreno" and "Terreno" in neumatico["tipo"]:
            p += 3
        if estilo_manejo == "economico":
            p += max(0, 3 - int(neumatico["precio"] / 60))

        if prioridad == "durabilidad":
            p += neumatico["garantia_km"] // 16000
        if prioridad == "rendimiento" and "Rendimiento" in neumatico["tipo"]:
            p += 4
        if prioridad == "traccion_lluvia" and neumatico["temporada"] in ("Todo el Año", "Invierno"):
            p += 2
        if prioridad == "nieve" and neumatico["temporada"] == "Invierno":
            p += 5
        if prioridad == "precio":
            p += max(0, 5 - int(neumatico["precio"] / 50))
        return p

    candidatos.sort(key=puntaje, reverse=True)

    # Deduplicar por medida: quedarse con el mejor puntaje por cada tamaño
    vistos: set[str] = set()
    unicos = []
    for n in candidatos:
        if n["medida"] not in vistos:
            vistos.add(n["medida"])
            unicos.append(n)

    top = unicos[:3]

    if not top:
        return json.dumps({
            "recomendaciones": [],
            "mensaje": "No se encontraron neumáticos que coincidan con sus criterios.",
        }, ensure_ascii=False)

    def _variantes(principal: dict) -> list[dict]:
        """Otros neumáticos con la misma medida pero distinto índice de velocidad."""
        return [
            {
                "id": v["id"],
                "modelo": v["modelo"],
                "indice_velocidad": v["indice_velocidad"],
                "precio": v["precio"],
                "stock": v["stock"],
            }
            for v in candidatos
            if v["medida"] == principal["medida"] and v["id"] != principal["id"]
        ]

    return json.dumps({
        "recomendaciones": [
            {
                "id": n["id"],
                "marca": n["marca"],
                "modelo": n["modelo"],
                "medida": n["medida"],
                "indice_velocidad": n["indice_velocidad"],
                "tipo": n["tipo"],
                "temporada": n["temporada"],
                "precio": n["precio"],
                "garantia_km": n["garantia_km"],
                "descripcion": n["descripcion"],
                "caracteristicas": n["caracteristicas"],
                "variantes_mismo_tamaño": _variantes(n),
            }
            for n in top
        ]
    }, ensure_ascii=False)


def generar_presupuesto(
    neumatico_id: str,
    cantidad: int = 4,
    incluir_instalacion: bool = True,
    session_id: str = "default",
) -> str:
    neumatico = next((n for n in NEUMATICOS if n["id"] == neumatico_id), None)
    if not neumatico:
        return json.dumps({"error": f"No se encontró el neumático con ID '{neumatico_id}'."}, ensure_ascii=False)
    if neumatico["stock"] < cantidad:
        return json.dumps({
            "error": f"Solo hay {neumatico['stock']} unidades en stock.",
            "stock_disponible": neumatico["stock"],
        }, ensure_ascii=False)

    subtotal_neumaticos = neumatico["precio"] * cantidad
    subtotal_instalacion = 0.0
    desglose_instalacion = None

    if incluir_instalacion:
        subtotal_instalacion = (TARIFA_INSTALACION + TARIFA_BALANCEO + TARIFA_DESECHO) * cantidad
        desglose_instalacion = {
            "montaje": TARIFA_INSTALACION * cantidad,
            "balanceo": TARIFA_BALANCEO * cantidad,
            "disposicion_usado": TARIFA_DESECHO * cantidad,
        }

    total = subtotal_neumaticos + subtotal_instalacion

    return json.dumps({
        "presupuesto": {
            "neumatico": {
                "id": neumatico["id"],
                "marca": neumatico["marca"],
                "modelo": neumatico["modelo"],
                "medida": neumatico["medida"],
                "tipo": neumatico["tipo"],
            },
            "cantidad": cantidad,
            "precio_unitario": neumatico["precio"],
            "subtotal_neumaticos": round(subtotal_neumaticos, 2),
            "incluir_instalacion": incluir_instalacion,
            "subtotal_instalacion": round(subtotal_instalacion, 2),
            "desglose_instalacion": desglose_instalacion,
            "total": round(total, 2),
            "envio": None if incluir_instalacion else "Gratis a todo el país",
            "cuotas": f"Hasta 6 cuotas sin interés de ${round(total / 6, 2):,.2f}",
        }
    }, ensure_ascii=False)


# ─── Definiciones de herramientas para Ollama ────────────────────────────────

HERRAMIENTAS_DEFINICION = [
    {
        "type": "function",
        "function": {
            "name": "buscar_neumaticos",
            "description": "Busca neumáticos por medida, marca, tipo, temporada o precio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "medida": {"type": "string"},
                    "marca": {"type": "string"},
                    "tipo": {"type": "string"},
                    "temporada": {"type": "string"},
                    "precio_maximo": {"type": "number"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_detalle_neumatico",
            "description": "Obtiene detalles completos de un neumático por su ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "neumatico_id": {"type": "string", "description": "ej: 'N001'"},
                },
                "required": ["neumatico_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verificar_compatibilidad",
            "description": "Verifica si una medida es compatible con un vehículo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehiculo": {"type": "string", "description": "ej: 'Honda Civic'"},
                    "medida": {"type": "string", "description": "ej: '225/45R17'"},
                },
                "required": ["vehiculo", "medida"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obtener_recomendaciones",
            "description": "Recomienda neumáticos según vehículo, estilo de manejo, presupuesto y prioridad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vehiculo": {"type": "string"},
                    "estilo_manejo": {"type": "string"},
                    "presupuesto_por_neumatico": {"type": "number"},
                    "prioridad": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generar_presupuesto",
            "description": "Genera un presupuesto detallado con precio total para un neumático.",
            "parameters": {
                "type": "object",
                "properties": {
                    "neumatico_id": {"type": "string"},
                    "cantidad": {"type": "integer"},
                    "incluir_instalacion": {"type": "boolean"},
                },
                "required": ["neumatico_id"],
            },
        },
    },
]

_ventas_confirmadas: dict[str, float] = {}
_VENTA_DEDUP_TTL = 86400  # 24 horas


def confirmar_venta(
    neumatico_id: str,
    cantidad: int,
    nombre_cliente: str = "",
    sucursal: str = "",
    notas: str = "",
    session_id: str = "default",
    **_,
) -> str:
    ahora = time.time()
    # Limpiar entradas expiradas para evitar crecimiento indefinido del dict
    expiradas = [k for k, v in _ventas_confirmadas.items() if ahora - v >= _VENTA_DEDUP_TTL]
    for k in expiradas:
        del _ventas_confirmadas[k]
    clave_dedup = f"{session_id}_{neumatico_id}_{cantidad}"
    ultimo = _ventas_confirmadas.get(clave_dedup, 0)
    if ahora - ultimo < _VENTA_DEDUP_TTL:
        return json.dumps({"confirmado": True, "duplicado": True, "mensaje": "Esta venta ya fue confirmada."}, ensure_ascii=False)
    _ventas_confirmadas[clave_dedup] = ahora

    neumatico = next((n for n in NEUMATICOS if n["id"] == neumatico_id), None)
    if not neumatico:
        return json.dumps({"error": "Neumático no encontrado"}, ensure_ascii=False)

    resultado = actualizar_stock(neumatico_id, cantidad)
    if not resultado["ok"]:
        return json.dumps({"error": resultado["error"]}, ensure_ascii=False)

    try:
        from app import notificar_venta_interna, obtener_o_asignar_agente, registrar_venta
        agente = obtener_o_asignar_agente(session_id)
        notificar_venta_interna(neumatico, cantidad, nombre_cliente, sucursal, notas, agente=agente["nombre"])
        registrar_venta(session_id, agente["nombre"], neumatico, cantidad, nombre_cliente, sucursal)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error enviando notificación de venta: {e}")

    total = neumatico["precio"] * cantidad
    return json.dumps({
        "confirmado": True,
        "modelo": f"{neumatico['marca']} {neumatico['modelo']}",
        "medida": neumatico["medida"],
        "cantidad": cantidad,
        "total": total,
        "stock_restante": resultado["stock_restante"],
    }, ensure_ascii=False)


def notificar_dot(
    neumaticos: str = "",
    session_id: str = "default",
    **_,
) -> str:
    try:
        from app import notificar_dot as _notificar_dot
        _notificar_dot(session_id, neumaticos)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error notificando DOT: {e}")
    return json.dumps({"notificado": True}, ensure_ascii=False)


def escalar_a_humano(
    motivo: str = "",
    session_id: str = "default",
    **_,
) -> str:
    try:
        from app import notificar_escalado, obtener_historial
        historial = obtener_historial(session_id)
        notificar_escalado(session_id, motivo, historial)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error escalando a humano: {e}")
    return json.dumps({"escalado": True, "mensaje": "Conversación derivada a un humano."}, ensure_ascii=False)


FUNCIONES_HERRAMIENTAS = {
    "buscar_neumaticos": buscar_neumaticos,
    "ver_detalle_neumatico": ver_detalle_neumatico,
    "verificar_compatibilidad": verificar_compatibilidad,
    "obtener_recomendaciones": obtener_recomendaciones,
    "generar_presupuesto": generar_presupuesto,
    "confirmar_venta": confirmar_venta,
    "escalar_a_humano": escalar_a_humano,
    "notificar_dot": notificar_dot,
}
