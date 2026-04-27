"""
L3 — Tool use: clasificador de tickets con herramientas externas
================================================================
El modelo decide cuándo invocar las tools disponibles.
El flujo ya no es 100% nuestro — el modelo participa en él.

Tools disponibles:
    - search_similar_tickets: busca tickets parecidos resueltos anteriormente
    - get_system_status: consulta el estado actual de los servicios

Las tools son mocks — devuelven datos simulados.
Cuando tengas la integración real, solo cambias la implementación
de la tool, no el resto del sistema.

Requisitos:
    pip install anthropic

Variables de entorno:
    ANTHROPIC_API_KEY
"""

import os
import json
import anthropic

client = anthropic.Anthropic()
MODEL  = "claude-sonnet-4-5"


# ─────────────────────────────────────────────
# Definición de tools
#
# El modelo usa la "description" para decidir cuándo invocar cada tool.
# Una descripción vaga = el modelo no sabe cuándo usarla.
# Una descripción precisa = el modelo la usa en el momento correcto.
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_similar_tickets",
        "description": (
            "Search for similar support tickets that have been resolved in the past. "
            "Use this when you need historical context about a problem — "
            "for example, to check if this issue has occurred before and how it was resolved."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Short description of the problem to search for"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 3)"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_system_status",
        "description": (
            "Get the current status of the system services. "
            "Use this when the ticket mentions a service being down or degraded, "
            "to check if there is an active incident before classifying severity."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Name of the service to check (e.g. 'auth', 'payments', 'api')"
                }
            },
            "required": ["service"]
        }
    }
]


# ─────────────────────────────────────────────
# Implementación de tools (mocks)
#
# En producción aquí iría la llamada real a Jira, PagerDuty, etc.
# La interfaz del resto del sistema no cambia.
# ─────────────────────────────────────────────

def search_similar_tickets(query: str, max_results: int = 3) -> list[dict]:
    """Mock: simula una búsqueda en el historial de tickets."""
    mock_tickets = [
        {
            "id": "TICKET-1042",
            "title": "Authentication service returning 500 on login",
            "resolution": "Database connection pool exhausted. Increased max connections and restarted the service.",
            "severity": "P1",
            "resolved_in_minutes": 23
        },
        {
            "id": "TICKET-987",
            "title": "Users unable to log in after deploy",
            "resolution": "Bad environment variable in the new deploy. Rolled back and fixed the config.",
            "severity": "P1",
            "resolved_in_minutes": 45
        },
        {
            "id": "TICKET-756",
            "title": "Intermittent 500 errors on auth endpoint",
            "resolution": "Memory leak in the token validation middleware. Patched and deployed hotfix.",
            "severity": "P2",
            "resolved_in_minutes": 90
        },
    ]
    return mock_tickets[:max_results]


def get_system_status(service: str) -> dict:
    """Mock: simula una consulta al estado de los servicios."""
    mock_statuses = {
        "auth": {
            "status": "degraded",
            "active_incident": True,
            "incident_id": "INC-2024-089",
            "started_at": "2024-01-15T09:15:00Z",
            "affected_regions": ["eu-west-1"]
        },
        "payments": {
            "status": "operational",
            "active_incident": False
        },
        "api": {
            "status": "operational",
            "active_incident": False
        }
    }
    return mock_statuses.get(service, {"status": "unknown", "active_incident": False})


def execute_tool(tool_name: str, tool_input: dict) -> str:
    """
    Ejecuta la tool real y devuelve el resultado como string JSON.

    Este es el punto de control de seguridad: el modelo dice qué
    quiere ejecutar, pero nosotros decidimos si ejecutarlo.
    Aquí podrías añadir validación, rate limiting, logging, etc.
    """
    print(f"  [Tool] Ejecutando: {tool_name}({tool_input})")

    if tool_name == "search_similar_tickets":
        result = search_similar_tickets(**tool_input)
    elif tool_name == "get_system_status":
        result = get_system_status(**tool_input)
    else:
        result = {"error": f"Tool '{tool_name}' no encontrada"}

    return json.dumps(result, ensure_ascii=False)


# ─────────────────────────────────────────────
# Agente con tool use
#
# A diferencia de L2, aquí el flujo no es lineal.
# El modelo puede invocar tools en cualquier orden y
# tantas veces como necesite antes de responder.
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a senior support engineer that classifies and triages support tickets.

You have access to tools to help you make better decisions:
- Use search_similar_tickets to check if this problem has occurred before
- Use get_system_status to check if there is an active incident for the affected service

Always use the available tools before classifying a ticket — historical context and
current system status are critical for an accurate severity assessment.

Respond ONLY with valid JSON. No additional text.
Schema:
{
  "severity": "P1" | "P2" | "P3" | "P4",
  "reason": string,
  "area": "backend" | "frontend" | "infra" | "data" | "security",
  "requires_escalation": boolean,
  "similar_incidents": [string],
  "recommended_action": string
}
""".strip()


def run_agent(ticket: str) -> dict:
    """
    Ejecuta el agente con tool use.

    El bucle continúa mientras el modelo quiera invocar tools
    (stop_reason == "tool_use"). Cuando termina (stop_reason == "end_turn")
    parseamos la respuesta final.
    """
    print("=" * 60)
    print("TICKET:", ticket[:80] + "..." if len(ticket) > 80 else ticket)
    print("=" * 60)

    messages = [{"role": "user", "content": f"[USER]\n{ticket}\n[/USER]"}]

    # Bucle de tool use — el modelo puede invocar varias tools
    # antes de dar la respuesta final
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )

        print(f"\n[Modelo] stop_reason: {response.stop_reason}")

        # El modelo ha terminado — respuesta final
        if response.stop_reason == "end_turn":
            text = next(b.text for b in response.content if b.type == "text")
            result = json.loads(text.strip())
            print("\n" + "=" * 60)
            print("RESULTADO FINAL:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result

        # El modelo quiere invocar una o más tools
        if response.stop_reason == "tool_use":

            # Añadimos la respuesta del modelo al historial
            messages.append({"role": "assistant", "content": response.content})

            # Procesamos todos los bloques tool_use de la respuesta
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            # Devolvemos los resultados al modelo y continuamos el bucle
            messages.append({"role": "user", "content": tool_results})


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
    run_agent(ticket_critical)
    print("\n\n")
    run_agent(ticket_minor)