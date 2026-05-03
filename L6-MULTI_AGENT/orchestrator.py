"""
L6 — Multi-agente: orquestador + especialistas en paralelo
===========================================================
El orquestador recibe un incidente complejo, decide qué especialistas
necesita, los lanza en paralelo y sintetiza sus informes.

Cada especialista es un agente L5 completo: tiene su propio bucle de
tool use, su propio system prompt y sus propias tools. No saben que
hay otros agentes trabajando en paralelo.

La clave de L6 es asyncio.gather() — lanza todos los especialistas
a la vez y espera a que termine el último.

Modelos:
    Orquestador → claude-sonnet-4-5   (coordinación y síntesis)
    Especialistas → claude-haiku-4-5-20251001  (tarea enfocada, más barato)

Requisitos:
    pip install anthropic

Variables de entorno:
    ANTHROPIC_API_KEY
"""

from dotenv import load_dotenv
load_dotenv()
import asyncio
import json
import anthropic

client               = anthropic.AsyncAnthropic()
ORCHESTRATOR_MODEL   = "claude-sonnet-4-5"
SPECIALIST_MODEL     = "claude-haiku-4-5-20251001"
MAX_ITERATIONS       = 8

def parse_json_safe(text: str) -> dict:
    import re
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        return json.loads(match.group(1).strip())
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))
    return json.loads(text.strip())


# ─────────────────────────────────────────────
# Tools por dominio
#
# Cada especialista recibe solo las tools de su dominio.
# Un agente con 3 tools relevantes es más preciso que
# uno con 12 tools mezcladas.
# ─────────────────────────────────────────────

TOOLS_INFRASTRUCTURE = [
    {
        "name": "get_pod_status",
        "description": "Devuelve el estado de los pods de Kubernetes para un servicio. Úsala para verificar si hay pods caídos, en CrashLoopBackOff o con reinicios recientes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Nombre del servicio: auth, payments, api_gateway, database"}
            },
            "required": ["service"]
        }
    },
    {
        "name": "get_resource_usage",
        "description": "Devuelve el uso de CPU y memoria de un servicio. Útil para detectar OOM kills o saturación de CPU que cause lentitud.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"}
            },
            "required": ["service"]
        }
    },
    {
        "name": "check_network_connectivity",
        "description": "Verifica la conectividad de red entre dos servicios. Úsala si sospechas problemas de routing o firewall entre componentes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "source":      {"type": "string", "description": "Servicio de origen"},
                "destination": {"type": "string", "description": "Servicio de destino"}
            },
            "required": ["source", "destination"]
        }
    }
]

TOOLS_DATABASE = [
    {
        "name": "get_db_connections",
        "description": "Devuelve el estado actual del pool de conexiones: total activas, idle, idle-in-transaction y el límite máximo.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_slow_queries",
        "description": "Devuelve las queries más lentas de las últimas N horas. Imprescindible para diagnosticar degradación de rendimiento.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Ventana de tiempo en horas (default: 1)"}
            }
        }
    },
    {
        "name": "check_replication_lag",
        "description": "Comprueba el lag de replicación entre primario y réplicas. Un lag alto puede causar lecturas inconsistentes.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

TOOLS_APPLICATION = [
    {
        "name": "get_service_logs",
        "description": "Devuelve las últimas N líneas de logs de un servicio. Busca patrones de error, stack traces y mensajes de warning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string"},
                "lines":   {"type": "integer", "description": "Número de líneas a devolver (default: 50)"}
            },
            "required": ["service"]
        }
    },
    {
        "name": "get_recent_deploys",
        "description": "Devuelve los deploys realizados en las últimas N horas. Un deploy reciente es siempre el primer sospechoso.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Ventana de tiempo (default: 6)"}
            }
        }
    },
    {
        "name": "get_error_rate",
        "description": "Devuelve la tasa de errores HTTP 5xx por servicio en los últimos N minutos.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service":  {"type": "string"},
                "minutes":  {"type": "integer", "description": "Ventana de tiempo en minutos (default: 30)"}
            },
            "required": ["service"]
        }
    }
]

TOOLS_SECURITY = [
    {
        "name": "get_failed_auth_attempts",
        "description": "Devuelve los intentos de autenticación fallidos agrupados por IP. Útil para detectar ataques de fuerza bruta o credential stuffing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Ventana de tiempo en minutos (default: 60)"}
            }
        }
    },
    {
        "name": "check_unusual_traffic",
        "description": "Analiza el tráfico de red en busca de patrones anómalos: volúmenes inusuales, IPs nuevas o endpoints poco frecuentes.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_recent_permission_changes",
        "description": "Devuelve cambios de permisos o roles realizados en las últimas 24 horas. Útil para detectar escalada de privilegios.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


# ─────────────────────────────────────────────
# Implementación de tools (mocks)
# ─────────────────────────────────────────────

def get_pod_status(service: str) -> dict:
    statuses = {
        "auth": {
            "pods": [
                {"name": "auth-7d9f-xk2p", "status": "Running",            "restarts": 0},
                {"name": "auth-7d9f-mn8q", "status": "CrashLoopBackOff",   "restarts": 7},
                {"name": "auth-7d9f-wz4r", "status": "Running",            "restarts": 0},
            ],
            "ready": "2/3",
            "note": "One pod in CrashLoopBackOff since 09:11 UTC"
        },
        "database": {"pods": [{"name": "db-primary-0", "status": "Running", "restarts": 0}], "ready": "1/1"},
        "api_gateway": {"pods": [
            {"name": "kong-abc", "status": "Running", "restarts": 0},
            {"name": "kong-def", "status": "Running", "restarts": 0},
        ], "ready": "2/2"},
    }
    return statuses.get(service, {"pods": [], "ready": "0/0", "note": "Service not found"})


def get_resource_usage(service: str) -> dict:
    usage = {
        "auth":        {"cpu_pct": 92, "memory_pct": 78, "oom_kills_last_hour": 0},
        "database":    {"cpu_pct": 45, "memory_pct": 61, "oom_kills_last_hour": 0},
        "api_gateway": {"cpu_pct": 23, "memory_pct": 34, "oom_kills_last_hour": 0},
    }
    return usage.get(service, {"cpu_pct": 0, "memory_pct": 0})


def check_network_connectivity(source: str, destination: str) -> dict:
    # Simulamos que auth → database tiene latencia alta
    if source == "auth" and destination == "database":
        return {"reachable": True, "latency_ms": 3800, "packet_loss_pct": 0,
                "note": "Unusually high latency — normal is <20ms"}
    return {"reachable": True, "latency_ms": 8, "packet_loss_pct": 0}


def get_db_connections() -> dict:
    return {
        "active":              187,
        "idle":                 5,
        "idle_in_transaction": 11,
        "max_connections":     200,
        "utilization_pct":     93.5,
        "oldest_idle_tx_min":  18,
        "note": "Pool near capacity. 11 connections idle-in-transaction > 10 min."
    }


def get_slow_queries(hours: int = 1) -> list:
    return [
        {"query": "SELECT * FROM sessions WHERE user_id = $1",
         "mean_ms": 4200, "calls": 1840, "total_ms": 7728000},
        {"query": "UPDATE users SET last_login = $1 WHERE id = $2",
         "mean_ms": 1100, "calls": 920,  "total_ms": 1012000},
    ]


def check_replication_lag() -> dict:
    return {"primary": "db-primary-0", "replicas": [
        {"name": "db-replica-1", "lag_seconds": 2.1,  "status": "streaming"},
        {"name": "db-replica-2", "lag_seconds": 18.4, "status": "streaming",
         "note": "Higher lag than usual — may indicate replica under load"},
    ]}


def get_service_logs(service: str, lines: int = 50) -> list:
    logs = {
        "auth": [
            "2024-01-15T09:12:03Z ERROR connection pool timeout after 30s",
            "2024-01-15T09:12:03Z ERROR failed to acquire db connection: pool exhausted",
            "2024-01-15T09:12:04Z ERROR POST /auth/login → 500 Internal Server Error",
            "2024-01-15T09:12:05Z WARN  retrying db connection (attempt 3/3)",
            "2024-01-15T09:12:05Z ERROR all retries exhausted, returning 500",
        ]
    }
    return logs.get(service, [f"No logs found for service '{service}'"])


def get_recent_deploys(hours: int = 6) -> list:
    return [
        {"service": "auth",      "version": "v2.14.1", "time": "2024-01-15T08:55:00Z",
         "author": "ci-bot", "status": "success",
         "note": "Deployed 17 min before incident start"},
        {"service": "frontend",  "version": "v1.8.3",  "time": "2024-01-15T07:30:00Z",
         "author": "ci-bot", "status": "success"},
    ]


def get_error_rate(service: str, minutes: int = 30) -> dict:
    rates = {
        "auth":        {"error_rate_pct": 44.2, "total_requests": 3820, "errors": 1689},
        "payments":    {"error_rate_pct": 0.1,  "total_requests": 910,  "errors": 1},
        "api_gateway": {"error_rate_pct": 0.2,  "total_requests": 8200, "errors": 16},
    }
    return rates.get(service, {"error_rate_pct": 0, "total_requests": 0, "errors": 0})


def get_failed_auth_attempts(minutes: int = 60) -> dict:
    return {
        "total_failures": 1842,
        "unique_ips": 3,
        "top_ips": [
            {"ip": "10.0.1.45",   "failures": 1820, "note": "Internal — auth service retries"},
            {"ip": "185.34.12.8", "failures":   15, "note": "External — possible brute force"},
            {"ip": "10.0.2.12",   "failures":    7, "note": "Internal — normal"},
        ],
        "note": "Majority of failures are internal (service retrying failed connections)"
    }


def check_unusual_traffic() -> dict:
    return {
        "anomalies_detected": False,
        "traffic_vs_baseline_pct": 103,
        "note": "Traffic volume within normal range. No unusual patterns."
    }


def get_recent_permission_changes() -> list:
    return []  # sin cambios recientes — descarta vector de seguridad


def execute_tool(name: str, inputs: dict) -> str:
    """Despacha la tool correcta según el nombre."""
    dispatch = {
        "get_pod_status":              lambda: get_pod_status(**inputs),
        "get_resource_usage":          lambda: get_resource_usage(**inputs),
        "check_network_connectivity":  lambda: check_network_connectivity(**inputs),
        "get_db_connections":          lambda: get_db_connections(),
        "get_slow_queries":            lambda: get_slow_queries(**inputs),
        "check_replication_lag":       lambda: check_replication_lag(),
        "get_service_logs":            lambda: get_service_logs(**inputs),
        "get_recent_deploys":          lambda: get_recent_deploys(**inputs),
        "get_error_rate":              lambda: get_error_rate(**inputs),
        "get_failed_auth_attempts":    lambda: get_failed_auth_attempts(**inputs),
        "check_unusual_traffic":       lambda: check_unusual_traffic(),
        "get_recent_permission_changes": lambda: get_recent_permission_changes(),
    }
    fn = dispatch.get(name)
    if fn is None:
        return json.dumps({"error": f"Tool '{name}' no encontrada"})
    return json.dumps(fn(), ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# System prompts — uno por especialista
#
# Cada especialista tiene un contexto limpio y enfocado.
# No saben que hay otros agentes — eso es responsabilidad
# del orquestador.
# ─────────────────────────────────────────────

def specialist_system(domain: str) -> str:
    domains = {
        "infrastructure": """
You are an infrastructure specialist. Your job is to investigate the infrastructure
layer: Kubernetes pods, resource usage (CPU/memory), and network connectivity.

Use your tools to gather evidence. When you have enough information, respond with
ONLY valid JSON:
{
  "domain":      "infrastructure",
  "findings":    [string],
  "root_cause":  string | null,
  "severity":    "critical" | "high" | "medium" | "low" | "none",
  "confidence":  "high" | "medium" | "low",
  "recommended_actions": [string]
}
""",
        "database": """
You are a database specialist. Your job is to investigate the database layer:
connection pool saturation, slow queries, and replication health.

Use your tools to gather evidence. When you have enough information, respond with
ONLY valid JSON:
{
  "domain":      "database",
  "findings":    [string],
  "root_cause":  string | null,
  "severity":    "critical" | "high" | "medium" | "low" | "none",
  "confidence":  "high" | "medium" | "low",
  "recommended_actions": [string]
}
""",
        "application": """
You are an application specialist. Your job is to investigate the application layer:
service logs, recent deploys, and error rates.

Use your tools to gather evidence. When you have enough information, respond with
ONLY valid JSON:
{
  "domain":      "application",
  "findings":    [string],
  "root_cause":  string | null,
  "severity":    "critical" | "high" | "medium" | "low" | "none",
  "confidence":  "high" | "medium" | "low",
  "recommended_actions": [string]
}
""",
        "security": """
You are a security specialist. Your job is to investigate the security layer:
failed authentication attempts, unusual traffic patterns, and permission changes.

Use your tools to gather evidence. When you have enough information, respond with
ONLY valid JSON:
{
  "domain":      "security",
  "findings":    [string],
  "root_cause":  string | null,
  "severity":    "critical" | "high" | "medium" | "low" | "none",
  "confidence":  "high" | "medium" | "low",
  "recommended_actions": [string]
}
""",
    }
    return domains[domain].strip()


# ─────────────────────────────────────────────
# Especialista — agente L5 async
# ─────────────────────────────────────────────

async def run_specialist(domain: str, task: str, tools: list) -> dict:
    """
    Ejecuta un agente especialista de forma asíncrona.
    Es el mismo bucle que L5, pero async para poder correr en paralelo.
    El especialista no sabe nada del orquestador ni de otros agentes.
    """
    print(f"  [{domain.upper()}] Iniciando investigación...")

    messages   = [{"role": "user", "content": task}]
    iterations = 0

    while iterations < MAX_ITERATIONS:
        iterations += 1

        response = await client.messages.create(
            model=SPECIALIST_MODEL,
            max_tokens=1024,
            temperature=0,
            system=specialist_system(domain),
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            text = next((b.text for b in response.content if b.type == "text"), "")
            print("DEBUG raw:", repr(text))  # añade esto
            result = parse_json_safe(text)
            print(f"  [{domain.upper()}] Completado — severidad: {result.get('severity', '?')}")
            return result

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [{domain.upper()}] → {block.name}({list(block.input.keys())})")
                    output = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     output,
                    })

            messages.append({"role": "user", "content": tool_results})

    return {"domain": domain, "error": "max_iterations_reached"}


# ─────────────────────────────────────────────
# Orquestador
# ─────────────────────────────────────────────

ORCHESTRATOR_SYSTEM = """
You are an incident response orchestrator. You coordinate specialized agents.

Your responsibilities:
  1. DECOMPOSE: analyze the incident and decide which specialists are needed
  2. (specialists run in parallel — you wait for their reports)
  3. SYNTHESIZE: receive all specialist reports and produce the final incident report

For decomposition, respond with ONLY valid JSON:
{
  "specialists": ["infrastructure", "database", "application", "security"],
  "tasks": {
    "infrastructure": "specific task for this specialist",
    "database":       "specific task for this specialist",
    "application":    "specific task for this specialist",
    "security":       "specific task for this specialist"
  }
}
Only include the specialists that are actually needed for this incident.

For synthesis, respond with ONLY valid JSON:
{
  "incident_summary":  string,
  "root_cause":        string,
  "severity":          "P1" | "P2" | "P3" | "P4",
  "contributing_factors": [string],
  "immediate_actions": [string],
  "escalate_to":       [string],
  "timeline":          string
}
""".strip()


async def decompose(incident: str) -> dict:
    """Fase 1: el orquestador decide qué especialistas son necesarios."""
    response = await client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=512,
        temperature=0,
        system=ORCHESTRATOR_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Analyze this incident and decide which specialists are needed:\n\n{incident}"
        }]
    )
    text = next(b.text for b in response.content if b.type == "text")
    return parse_json_safe(text)


async def synthesize(incident: str, specialist_reports: list[dict]) -> dict:
    """Fase 3: el orquestador sintetiza los informes de todos los especialistas."""
    reports_text = json.dumps(specialist_reports, ensure_ascii=False, indent=2)

    response = await client.messages.create(
        model=ORCHESTRATOR_MODEL,
        max_tokens=1024,
        temperature=0,
        system=ORCHESTRATOR_SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Original incident:\n{incident}\n\n"
                f"Specialist reports:\n{reports_text}\n\n"
                "Synthesize these findings into the final incident report."
            )
        }]
    )
    text = next(b.text for b in response.content if b.type == "text")
    return parse_json_safe(text)


SPECIALIST_TOOLS = {
    "infrastructure": TOOLS_INFRASTRUCTURE,
    "database":       TOOLS_DATABASE,
    "application":    TOOLS_APPLICATION,
    "security":       TOOLS_SECURITY,
}


async def run_orchestrator(incident: str) -> dict:
    """
    Ejecuta el sistema multi-agente completo.

    Fase 1: orquestador decide qué especialistas activar
    Fase 2: especialistas corren en paralelo con asyncio.gather()
    Fase 3: orquestador sintetiza todos los informes

    El tiempo total es el del especialista más lento,
    no la suma de todos.
    """
    print("=" * 60)
    print("INCIDENTE:", incident[:80] + "..." if len(incident) > 80 else incident)
    print("=" * 60)

    # ── Fase 1: Descomposición ──
    print("\n[Orquestador] Analizando incidente...")
    plan = await decompose(incident)

    specialists_needed = plan.get("specialists", [])
    tasks              = plan.get("tasks", {})

    print(f"[Orquestador] Especialistas activados: {', '.join(specialists_needed)}")

    # ── Fase 2: Ejecución paralela ──
    # asyncio.gather lanza todos los especialistas simultáneamente.
    # Cada uno tiene su propio event loop, sus propias tools y su propio contexto.
    print(f"\n[Orquestador] Lanzando {len(specialists_needed)} especialistas en paralelo...\n")

    coroutines = [
        run_specialist(
            domain=domain,
            task=tasks.get(domain, f"Investigate the incident: {incident}"),
            tools=SPECIALIST_TOOLS[domain],
        )
        for domain in specialists_needed
        if domain in SPECIALIST_TOOLS
    ]

    specialist_reports = await asyncio.gather(*coroutines)

    # ── Fase 3: Síntesis ──
    print(f"\n[Orquestador] Sintetizando {len(specialist_reports)} informes...")
    final_report = await synthesize(incident, list(specialist_reports))

    print("\n" + "=" * 60)
    print("INFORME FINAL:")
    print(json.dumps(final_report, ensure_ascii=False, indent=2))
    return final_report


# ─────────────────────────────────────────────
# Escenarios de ejemplo
# ─────────────────────────────────────────────

# Incidente complejo que toca múltiples dominios — el orquestador
# debería activar los 4 especialistas
incident_complex = """
Multiple alerts firing simultaneously since 09:12 UTC:
- Auth service returning 500 errors on login (43% error rate)
- Dashboard reporting slow response times for all users
- 3 failed SSH attempts to the database server from an unknown external IP
- One auth pod in CrashLoopBackOff

Approximately 3,500 users unable to log in. No deploy was scheduled today
but the CI/CD pipeline ran automatically at 08:55 UTC.
""".strip()

# Incidente acotado — el orquestador debería activar solo 2 especialistas
incident_focused = """
Users reporting that the payments page loads very slowly — averaging 8 seconds.
No errors, just high latency. Started about 45 minutes ago.
No recent deploys to the payments service.
""".strip()


async def main():
    await run_orchestrator(incident_complex)
    print("\n\n")
    await run_orchestrator(incident_focused)


if __name__ == "__main__":
    asyncio.run(main())
