"""
L2 — Chain determinista: triaje de tickets de soporte técnico
==============================================================
Tres pasos encadenados usando el SDK oficial de Anthropic.
El flujo lo controla el código, no el modelo.

Paso 1 → Extrae entidades del ticket (componente, síntoma, entorno)
Paso 2 → Clasifica severidad y área
Paso 3 → Genera acción recomendada en formato estructurado

Requisitos:
    pip install anthropic

Variables de entorno:
    ANTHROPIC_API_KEY — tu clave de API de Anthropic
"""

from dotenv import load_dotenv
load_dotenv()

import os
import json
import anthropic

client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno automáticamente
MODEL  = "claude-sonnet-4-5"


# ─────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────

def call_claude(system: str, user: str, temperature: float = 0.0) -> str:
    """
    Llamada al modelo con un system prompt y un mensaje de usuario.

    temperature=0   → determinista, ideal para extracción y clasificación
    temperature=0.2 → ligera variedad, útil para generación de texto
    """
    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return message.content[0].text.strip()


def parse_json_safe(text: str) -> dict:
    """
    Parsea JSON de forma segura.
    Los LLMs a veces envuelven la respuesta en ```json ... ```.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1])
    return json.loads(cleaned)


# ─────────────────────────────────────────────
# Paso 1 — Extracción de entidades
# ─────────────────────────────────────────────

SYSTEM_EXTRACTOR = """
Eres un extractor de entidades técnicas de tickets de soporte de software.
Analiza el ticket y extrae información estructurada.

Responde SOLO con JSON válido. Sin texto adicional, sin markdown, sin explicaciones.
Schema exacto:
{
  "componente": string,
  "sintoma": string,
  "entorno": "producción" | "staging" | "desarrollo" | "desconocido",
  "menciona_datos": boolean
}
""".strip()


def step1_extract(ticket: str) -> dict:
    """Extrae las entidades clave del ticket en formato estructurado."""
    print("\n[Paso 1] Extrayendo entidades...")

    # Envolvemos el input en etiquetas para separar contexto de instrucción.
    # Defensa básica contra prompt injection: el modelo sabe que
    # lo que hay dentro de [USER][/USER] son datos, no instrucciones.
    raw = call_claude(SYSTEM_EXTRACTOR, f"[USER]\n{ticket}\n[/USER]")

    result = parse_json_safe(raw)
    print(f"  → {result}")
    return result


# ─────────────────────────────────────────────
# Paso 2 — Clasificación de severidad
# ─────────────────────────────────────────────

SYSTEM_CLASSIFIER = """
Eres un clasificador de severidad para tickets de soporte técnico.
Recibirás el ticket original más las entidades ya extraídas en el paso anterior.

Responde SOLO con JSON válido. Sin texto adicional.
Schema exacto:
{
  "severidad": "P1" | "P2" | "P3" | "P4",
  "razon_severidad": string,
  "area": "backend" | "frontend" | "infra" | "datos" | "seguridad",
  "requiere_escalado": boolean
}

Criterios de severidad:
- P1: sistema caído en producción, pérdida de datos, brecha de seguridad
- P2: funcionalidad crítica degradada en producción
- P3: bug en producción sin workaround conocido
- P4: bug menor, mejora o pregunta
""".strip()


def step2_classify(ticket: str, entities: dict) -> dict:
    """
    Clasifica la severidad usando el ticket original y las entidades del paso 1.

    Recibe entities como parámetro explícito — el estado lo gestionamos
    nosotros, no el framework. Esto es lo que define L2 como determinista.
    """
    print("\n[Paso 2] Clasificando severidad...")

    user_msg = f"""
Ticket original:
[USER]
{ticket}
[/USER]

Entidades extraídas (paso anterior):
{json.dumps(entities, ensure_ascii=False, indent=2)}
""".strip()

    raw = call_claude(SYSTEM_CLASSIFIER, user_msg)
    result = parse_json_safe(raw)
    print(f"  → {result}")
    return result


# ─────────────────────────────────────────────
# Paso 3 — Generación de acción
# ─────────────────────────────────────────────

SYSTEM_WRITER = """
Eres un agente de soporte técnico senior que estructura tickets para el equipo de ingeniería.
Recibirás el ticket original, las entidades y la clasificación de severidad.

Responde SOLO con JSON válido. Sin texto adicional.
Schema exacto:
{
  "titulo": string,
  "descripcion": string,
  "pasos_siguientes": [string],
  "etiquetas": [string]
}

Restricciones:
- titulo: máximo 80 caracteres, claro y accionable
- pasos_siguientes: entre 2 y 4 acciones concretas
- etiquetas: máximo 5, en kebab-case
""".strip()


def step3_generate_action(ticket: str, entities: dict, classification: dict) -> dict:
    """
    Genera el resumen estructurado listo para el sistema de tickets.
    Usa temperature=0.2 para que el texto generado tenga algo de variedad
    sin perder coherencia — es escritura, no clasificación.
    """
    print("\n[Paso 3] Generando acción estructurada...")

    user_msg = f"""
Ticket original:
[USER]
{ticket}
[/USER]

Entidades:
{json.dumps(entities, ensure_ascii=False, indent=2)}

Clasificación:
{json.dumps(classification, ensure_ascii=False, indent=2)}
""".strip()

    raw = call_claude(SYSTEM_WRITER, user_msg, temperature=0.2)
    result = parse_json_safe(raw)
    print(f"  → {result}")
    return result


# ─────────────────────────────────────────────
# Pipeline: la chain completa
# ─────────────────────────────────────────────

def run_chain(ticket: str) -> dict:
    """
    Ejecuta los tres pasos en secuencia.

    El orden es fijo: siempre 1 → 2 → 3.
    El modelo no decide el flujo — eso lo hace este código.
    Si un paso falla, la excepción sube sin silenciarse.
    """
    print("=" * 60)
    print("TICKET:", ticket[:80] + "..." if len(ticket) > 80 else ticket)
    print("=" * 60)

    entities       = step1_extract(ticket)
    classification = step2_classify(ticket, entities)
    action         = step3_generate_action(ticket, entities, classification)

    result = {
        "input":          ticket,
        "entities":       entities,
        "classification": classification,
        "action":         action,
    }

    print("\n" + "=" * 60)
    print("RESULTADO FINAL:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


# ─────────────────────────────────────────────
# Ejemplos de uso
# ─────────────────────────────────────────────

ticket_critical = """
Users cannot log in since 09:15 UTC. The authentication service is returning
500 errors on POST /auth/login. All environments affected. We are seeing
database connection timeouts in the logs. Approximately 3,000 users impacted.
""".strip()

ticket_minor = """
On the account settings page, when the user updates their email address,
the confirmation message shows the old email instead of the new one.
The update itself works correctly — it is only a display issue.
Reported in production, low impact.
""".strip()


if __name__ == "__main__":
    run_chain(ticket_critical)
    print("\n\n")
    run_chain(ticket_minor)