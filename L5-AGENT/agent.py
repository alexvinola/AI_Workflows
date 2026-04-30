"""
L5 — Agente autónomo de respuesta a incidentes
===============================================
El agente recibe un reporte en texto libre y trabaja de forma autónoma
hasta completar su objetivo: investigar, diagnosticar, actuar e informar.

A diferencia de L3, aquí el modelo no responde a una pregunta — trabaja
hacia un objetivo compuesto que él mismo decide cuándo ha cumplido.

El bucle es el mismo que en L3 (stop_reason == "tool_use"), pero la
condición de parada es distinta: el modelo termina cuando considera
que el objetivo está completo, no solo cuando ya no necesita tools.

Requisitos:
    pip install anthropic

Variables de entorno:
    ANTHROPIC_API_KEY
"""

import json
import anthropic

client = anthropic.Anthropic()
MODEL          = "claude-sonnet-4-5"
MAX_ITERATIONS = 10  # techo de seguridad — si se alcanza, algo ha ido mal


# ─────────────────────────────────────────────
# Definición de tools
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "check_service_health",
        "description": (
            "Consulta el estado actual de un servicio en producción. "
            "Devuelve métricas en tiempo real: tasa de error, latencia, "
            "y si hay un incidente activo. Úsala siempre al inicio para "
            "establecer el estado base antes de investigar más."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Nombre del servicio: auth, payments, api_gateway, database, frontend"
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "get_incident_history",
        "description": (
            "Recupera los incidentes más recientes de un servicio. "
            "Útil para detectar patrones — si el mismo servicio ha fallado "
            "tres veces esta semana, eso cambia la severidad y la acción."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Nombre del servicio a consultar"
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de incidentes a devolver (default: 3)"
                }
            },
            "required": ["service"]
        }
    },
    {
        "name": "search_runbook",
        "description": (
            "Busca en los runbooks y guías de operaciones el procedimiento "
            "de resolución para un tipo de problema. Devuelve los pasos "
            "recomendados y el equipo responsable."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Descripción del problema a buscar, ej: 'auth 500 database connection'"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "create_incident",
        "description": (
            "Crea un incidente en el sistema de gestión. "
            "Llama a esta tool SIEMPRE, incluso para incidentes menores — "
            "todo debe quedar registrado. Devuelve el ID del incidente creado."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Título conciso del incidente"},
                "description": {"type": "string", "description": "Descripción técnica detallada"},
                "severity":    {"type": "string", "description": "P1 | P2 | P3 | P4"},
                "service":     {"type": "string", "description": "Servicio afectado"}
            },
            "required": ["title", "description", "severity", "service"]
        }
    },
    {
        "name": "escalate_incident",
        "description": (
            "Escala un incidente al equipo responsable. "
            "Obligatorio para P1 y P2. Opcional para P3 si hay reincidencia. "
            "Nunca escalar P4 — se gestiona en el backlog normal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "ID del incidente a escalar"},
                "team": {
                    "type": "string",
                    "description": "Equipo al que escalar: backend, frontend, infra, database, security"
                },
                "reason": {"type": "string", "description": "Razón de la escalada"}
            },
            "required": ["incident_id", "team", "reason"]
        }
    },
    {
        "name": "add_incident_note",
        "description": (
            "Añade una nota de investigación a un incidente existente. "
            "Usar para documentar hallazgos intermedios — qué se investigó, "
            "qué se descartó y por qué."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "note":        {"type": "string", "description": "Hallazgo o acción documentada"}
            },
            "required": ["incident_id", "note"]
        }
    }
]


# ─────────────────────────────────────────────
# Implementación de tools (mocks)
# ─────────────────────────────────────────────

_incident_counter = 100  # simula un ID autoincremental


def check_service_health(service: str) -> dict:
    statuses = {
        "auth": {
            "status": "degraded",
            "error_rate_pct": 43,
            "p99_latency_ms": 8200,
            "active_incident": True,
            "notes": "Spike in connection errors since 09:12 UTC"
        },
        "payments": {
            "status": "operational",
            "error_rate_pct": 0.1,
            "p99_latency_ms": 320,
            "active_incident": False
        },
        "api_gateway": {
            "status": "operational",
            "error_rate_pct": 0.3,
            "p99_latency_ms": 95,
            "active_incident": False
        },
        "database": {
            "status": "degraded",
            "error_rate_pct": 12,
            "p99_latency_ms": 4100,
            "active_incident": True,
            "notes": "Connection pool at 98% capacity. Max connections: 200"
        },
        "frontend": {
            "status": "operational",
            "error_rate_pct": 0.0,
            "p99_latency_ms": 210,
            "active_incident": False
        },
    }
    return statuses.get(service, {"status": "unknown", "error": f"Service '{service}' not found"})


def get_incident_history(service: str, limit: int = 3) -> list[dict]:
    history = {
        "auth": [
            {
                "id": "INC-089",
                "date": "2024-01-08",
                "title": "Auth 500s due to DB connection pool exhaustion",
                "resolution": "Increased max_connections to 200, restarted auth service",
                "duration_min": 23,
                "severity": "P1"
            },
            {
                "id": "INC-071",
                "date": "2023-12-19",
                "title": "Auth failures after deploy — bad env var",
                "resolution": "Rolled back deploy, fixed DATABASE_URL in config",
                "duration_min": 45,
                "severity": "P1"
            },
        ],
        "database": [
            {
                "id": "INC-082",
                "date": "2024-01-05",
                "title": "DB connection pool exhausted during peak traffic",
                "resolution": "Killed idle-in-transaction connections, added connection pooling via PgBouncer",
                "duration_min": 35,
                "severity": "P2"
            }
        ],
        "api_gateway": [
            {
                "id": "INC-061",
                "date": "2023-11-30",
                "title": "Circuit breaker open on payments upstream",
                "resolution": "Restarted Kong, payments service had recovered",
                "duration_min": 12,
                "severity": "P2"
            }
        ],
    }
    return history.get(service, [])[:limit]


def search_runbook(query: str) -> dict:
    query_lower = query.lower()

    if any(k in query_lower for k in ["auth", "login", "500", "connection"]):
        return {
            "runbook": "Auth Service — Connection Errors",
            "steps": [
                "1. Check DB connection pool: SELECT count(*) FROM pg_stat_activity WHERE state='active'",
                "2. If pool > 180: kill idle-in-transaction connections older than 10min",
                "3. Restart auth service: kubectl rollout restart deployment/auth-service",
                "4. Monitor for 2 minutes: kubectl logs -f deployment/auth-service",
                "5. Verify /auth/health returns 200"
            ],
            "owner_team": "backend",
            "escalate_if": "Pool exhausted repeatedly or restart doesn't resolve within 5 min"
        }

    if any(k in query_lower for k in ["database", "db", "pool", "timeout"]):
        return {
            "runbook": "Database — Connection Pool Issues",
            "steps": [
                "1. Query active connections by service: SELECT application_name, count(*) FROM pg_stat_activity GROUP BY 1",
                "2. Identify the culprit service and check for connection leaks",
                "3. Kill long-running idle transactions: SELECT pg_terminate_backend(pid) ...",
                "4. Consider enabling PgBouncer if issue is recurring"
            ],
            "owner_team": "database",
            "escalate_if": "Connections don't drop after killing idle transactions"
        }

    return {
        "runbook": "General Incident Response",
        "steps": [
            "1. Identify affected service using monitoring dashboards",
            "2. Check recent deploys: any correlation with incident start time?",
            "3. Review logs for the affected service",
            "4. Escalate to the service owner if no resolution in 15 min"
        ],
        "owner_team": "on-call",
        "escalate_if": "No root cause found within 20 minutes"
    }


def create_incident(title: str, description: str, severity: str, service: str) -> dict:
    global _incident_counter
    _incident_counter += 1
    incident_id = f"INC-{_incident_counter}"
    sla = {"P1": "1h", "P2": "4h", "P3": "24h", "P4": "72h"}.get(severity, "24h")
    return {
        "id":        incident_id,
        "title":     title,
        "severity":  severity,
        "service":   service,
        "status":    "open",
        "sla":       sla,
        "created":   "2024-01-15T09:18:00Z",
    }


def escalate_incident(incident_id: str, team: str, reason: str) -> dict:
    return {
        "incident_id":  incident_id,
        "escalated_to": team,
        "channel":      f"#incidents-{team}",
        "notified":     True,
        "message":      f"[{incident_id}] Escalated to {team}: {reason}"
    }


def add_incident_note(incident_id: str, note: str) -> dict:
    return {"incident_id": incident_id, "note_saved": True, "note": note}


def execute_tool(name: str, inputs: dict) -> str:
    """
    Punto de control: el modelo solicita, el código ejecuta.
    En producción aquí van validaciones, rate limiting, audit log.
    """
    print(f"  [Tool] {name}({json.dumps(inputs, ensure_ascii=False)})")

    dispatch = {
        "check_service_health":  lambda: check_service_health(**inputs),
        "get_incident_history":  lambda: get_incident_history(**inputs),
        "search_runbook":        lambda: search_runbook(**inputs),
        "create_incident":       lambda: create_incident(**inputs),
        "escalate_incident":     lambda: escalate_incident(**inputs),
        "add_incident_note":     lambda: add_incident_note(**inputs),
    }

    fn = dispatch.get(name)
    if fn is None:
        return json.dumps({"error": f"Tool '{name}' no encontrada"})

    return json.dumps(fn(), ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# System prompt — define el agente
#
# En L3 el prompt describía un rol.
# En L5 describe un protocolo de trabajo completo:
# fases, criterios de decisión y condición de parada.
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
You are an autonomous incident response agent. When you receive an incident report,
you work through it independently until the objective is fully complete.

Your objective for every incident:
  1. INVESTIGATE — gather facts using the available tools
  2. DIAGNOSE    — determine root cause and severity
  3. ACT         — create the incident ticket; escalate if P1 or P2
  4. REPORT      — produce the final JSON report

Severity criteria:
  P1: production system down or data loss — immediate escalation required
  P2: critical functionality degraded in production — escalate within 15 min
  P3: bug in production with no data loss, workaround exists — no escalation
  P4: minor issue or question — no escalation, handle in backlog

Rules:
  - Always call check_service_health before drawing conclusions
  - Always call get_incident_history to check for patterns (recurring = higher severity)
  - Always call search_runbook to find the resolution procedure
  - Always call create_incident — every incident must be recorded, even P4
  - Call escalate_incident for P1 and P2 without exception
  - Use add_incident_note to document key findings during investigation

When you have completed all four phases, respond with ONLY valid JSON:
{
  "incident_id":    string,
  "root_cause":     string,
  "severity":       "P1" | "P2" | "P3" | "P4",
  "actions_taken":  [string],
  "escalated":      boolean,
  "escalated_to":   string | null,
  "resolution":     string,
  "next_steps":     [string]
}
""".strip()


# ─────────────────────────────────────────────
# Bucle del agente
# ─────────────────────────────────────────────

def run_agent(report: str) -> dict:
    """
    Ejecuta el agente hasta que completa el objetivo o alcanza MAX_ITERATIONS.

    El bucle es técnicamente igual que en L3, pero el modelo llega a
    end_turn de forma distinta: no porque se haya quedado sin tools que
    llamar, sino porque ha completado las cuatro fases del objetivo y
    decide activamente que ha terminado.
    """
    print("=" * 60)
    print("INCIDENTE:", report[:80] + "..." if len(report) > 80 else report)
    print("=" * 60)

    messages   = [{"role": "user", "content": f"[INCIDENT REPORT]\n{report}\n[/INCIDENT REPORT]"}]
    iterations = 0

    while iterations < MAX_ITERATIONS:
        iterations += 1
        print(f"\n[Iteración {iterations}]")

        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            temperature=0,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        print(f"  stop_reason: {response.stop_reason}")

        # El agente ha decidido que el objetivo está completo
        if response.stop_reason == "end_turn":
            text = next(b.text for b in response.content if b.type == "text")
            result = json.loads(text.strip())
            print("\n" + "=" * 60)
            print("INFORME FINAL:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return result

        # El agente quiere ejecutar tools — seguimos en el bucle
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result,
                    })

            messages.append({"role": "user", "content": tool_results})

    # Límite de iteraciones alcanzado — el agente no terminó
    print(f"\n[WARNING] Límite de {MAX_ITERATIONS} iteraciones alcanzado.")
    return {"error": "max_iterations_reached", "iterations": iterations}


# ─────────────────────────────────────────────
# Escenarios de ejemplo
# ─────────────────────────────────────────────

# P1: servicio caído, impacto masivo
incident_critical = """
Users cannot log in since 09:12 UTC. The authentication service is returning
500 errors on POST /auth/login. Approximately 3,500 users impacted across all regions.
Database connection timeouts visible in the logs. The issue started suddenly,
no deploy was made in the last 6 hours.
""".strip()

# P3: bug menor, sin impacto en datos
incident_minor = """
On the account settings page, when a user updates their email address,
the confirmation toast shows the old email instead of the new one.
The update itself saves correctly — it is purely a display issue.
Reported by 2 users in production. Low impact.
""".strip()

# Ambiguo: el agente tiene que investigar para determinar el alcance
incident_ambiguous = """
We're getting some complaints from users about slow response times on the dashboard.
Not sure which service is the problem. Started maybe 30 minutes ago.
Some users say it times out, others say it just feels slow.
""".strip()


if __name__ == "__main__":
    run_agent(incident_critical)
    print("\n\n")
    run_agent(incident_minor)
    print("\n\n")
    run_agent(incident_ambiguous)
