"""
L7 — MCP Server: expone documentación técnica via Model Context Protocol
========================================================================
Un servidor MCP que cualquier cliente compatible puede conectar y usar.
No sabe nada del cliente — solo expone capacidades y las ejecuta cuando
se le pide.

Expone:
    Resources:
        docs://list            → lista los documentos disponibles
        docs://{filename}      → lee el contenido de un documento

    Tools:
        search_docs            → busca un término en toda la documentación
        create_ticket_draft    → genera un borrador de ticket de soporte
        get_open_tickets       → consulta tickets abiertos en la base de datos
        save_ticket            → guarda un ticket real en la base de datos
        close_ticket           → cierra un ticket con su resolución

Base de datos: SQLite local (tickets.db).
El servidor la crea y la puebla con datos de ejemplo al arrancar.
El cliente no sabe que existe una base de datos — solo ve las tools.

Transporte: stdio (el cliente arranca este script como subproceso y se
comunica por stdin/stdout). Es el transporte estándar para servidores MCP
locales — así funciona la integración con Claude Desktop, Cursor, etc.

Requisitos:
    pip install mcp
"""

import os
import glob
import sqlite3
from datetime import datetime
from mcp.server.fastmcp import FastMCP


# ─────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────

DOCS_PATH = "./docs"
DB_PATH   = "./tickets.db"

# El nombre identifica al servidor en el ecosistema MCP.
# Los clientes lo usan para mostrar qué servidores están conectados.
mcp = FastMCP("support-docs")


# ─────────────────────────────────────────────
# Base de datos — SQLite
#
# El servidor gestiona la BD de forma completamente transparente
# para el cliente. Desde fuera solo se ven tools con nombres semánticos.
# Mañana podrías migrar a PostgreSQL cambiando solo este bloque.
# ─────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    """
    Abre una conexión a la base de datos.
    Creamos una conexión nueva por llamada para evitar problemas
    de concurrencia — SQLite no es thread-safe con una sola conexión compartida.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite acceder a columnas por nombre: row["title"]
    return conn


def init_db() -> None:
    """
    Crea la tabla de tickets y la puebla con datos de ejemplo.
    Si la BD ya existe, no hace nada (IF NOT EXISTS).
    Se llama al arrancar el servidor — el cliente nunca la invoca directamente.
    """
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL,
            severity    TEXT    NOT NULL DEFAULT 'P3',
            service     TEXT,
            status      TEXT    NOT NULL DEFAULT 'open',
            resolution  TEXT,
            created_at  TEXT    NOT NULL,
            closed_at   TEXT
        )
    """)

    # Insertar datos de ejemplo solo si la tabla está vacía
    count = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    if count == 0:
        sample_tickets = [
            ("Auth service returning 500 on login",
             "Users cannot log in since 09:15 UTC. Database connection timeouts in logs.",
             "P1", "auth"),
            ("Email confirmation shows old address",
             "After updating email, the confirmation message shows the previous address.",
             "P4", "frontend"),
            ("API gateway rejecting requests with 503",
             "Circuit breaker open on payments upstream. Started after last deploy.",
             "P2", "api_gateway"),
            ("DB connection pool exhausted during peak hours",
             "pg_stat_activity shows 200+ idle connections. Service restarts help temporarily.",
             "P2", "database"),
            ("Rate limiting incorrectly applied to enterprise plan",
             "Enterprise customer receiving 429 errors despite unlimited plan.",
             "P3", "api_gateway"),
        ]
        now = datetime.utcnow().isoformat()
        conn.executemany(
            "INSERT INTO tickets (title, description, severity, service, created_at) VALUES (?,?,?,?,?)",
            [(t[0], t[1], t[2], t[3], now) for t in sample_tickets],
        )

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# Resources — datos que el cliente puede leer
#
# Un resource es contenido que el modelo puede consultar, como un GET en REST.
# El cliente lo pide por URI; el servidor devuelve el contenido.
# ─────────────────────────────────────────────

@mcp.resource("docs://list")
def list_documents() -> str:
    """
    Lista todos los documentos disponibles en el servidor.
    El cliente puede leer este resource para saber qué documentos existen
    antes de pedir uno concreto.
    """
    pattern = os.path.join(DOCS_PATH, "*.md")
    files   = sorted(glob.glob(pattern))

    if not files:
        return "No hay documentos disponibles."

    names = [os.path.basename(f) for f in files]
    return "\n".join(names)


@mcp.resource("docs://{filename}")
def read_document(filename: str) -> str:
    """
    Lee el contenido completo de un documento.
    El cliente construye la URI con el nombre del fichero:
        docs://authentication.md
        docs://database.md
        docs://api_gateway.md
    """
    # Evitar path traversal: el fichero solo puede estar en DOCS_PATH
    safe_name = os.path.basename(filename)
    filepath  = os.path.join(DOCS_PATH, safe_name)

    if not os.path.exists(filepath):
        return f"Documento '{safe_name}' no encontrado. Usa docs://list para ver los disponibles."

    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────
# Tools — acciones que el cliente puede ejecutar
#
# Una tool es una operación, como un POST en REST.
# El cliente (o el LLM) decide cuándo invocarla y con qué parámetros.
# FastMCP genera el JSON schema de cada tool a partir de los type hints.
# ─────────────────────────────────────────────

@mcp.tool()
def search_docs(query: str) -> str:
    """
    Busca un término en toda la documentación y devuelve los fragmentos
    relevantes con el nombre del documento de origen.

    Útil cuando no sabes en qué documento está la información — el LLM
    puede buscar primero y luego leer el documento completo si necesita más.
    """
    pattern = os.path.join(DOCS_PATH, "*.md")
    files   = sorted(glob.glob(pattern))
    results = []

    query_lower = query.lower()

    for filepath in files:
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            if query_lower in line.lower():
                # Devolvemos la línea con algo de contexto (±1 línea)
                start   = max(0, i - 1)
                end     = min(len(lines), i + 2)
                excerpt = "".join(lines[start:end]).strip()
                results.append(f"[{filename}]\n{excerpt}")

    if not results:
        return f"No se encontraron resultados para '{query}'."

    return "\n\n---\n\n".join(results)


@mcp.tool()
def create_ticket_draft(title: str, description: str, severity: str = "P3") -> str:
    """
    Genera un borrador de ticket de soporte estructurado.
    Devuelve el ticket formateado listo para copiar al sistema de tickets.

    severity: P1 (crítico) | P2 (alto) | P3 (medio) | P4 (bajo)
    """
    valid_severities = {"P1", "P2", "P3", "P4"}
    if severity not in valid_severities:
        severity = "P3"

    # En producción aquí iría una llamada real a Jira, Linear, etc.
    # El servidor MCP abstrae esa integración — el cliente no sabe
    # si esto escribe en Jira, en una base de datos o en un fichero.
    draft = f"""
BORRADOR DE TICKET
==================
Título:      {title}
Severidad:   {severity}
Estado:      Abierto
Asignado a:  Sin asignar

Descripción:
{description}

Pasos siguientes:
- [ ] Verificar en entorno de staging
- [ ] Revisar logs del servicio afectado
- [ ] Escalar si no hay resolución en {_sla(severity)}
""".strip()

    return draft


def _sla(severity: str) -> str:
    """Tiempo máximo de resolución según severidad."""
    return {"P1": "1 hora", "P2": "4 horas", "P3": "24 horas", "P4": "72 horas"}.get(severity, "24 horas")


# ─────────────────────────────────────────────
# Tools — base de datos
# ─────────────────────────────────────────────

@mcp.tool()
def get_open_tickets(service: str = "", severity: str = "") -> str:
    """
    Devuelve los tickets abiertos de la base de datos.
    Se puede filtrar por servicio (auth, database, api_gateway, frontend)
    y/o por severidad (P1, P2, P3, P4).
    Dejar vacío para ver todos los tickets abiertos.
    """
    conn  = get_db()
    query = "SELECT * FROM tickets WHERE status = 'open'"
    params: list = []

    if service:
        query += " AND service = ?"
        params.append(service)
    if severity:
        query += " AND severity = ?"
        params.append(severity)

    query += " ORDER BY severity, created_at"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        return "No hay tickets abiertos con esos filtros."

    lines = []
    for row in rows:
        lines.append(
            f"[#{row['id']}] {row['severity']} | {row['service'] or 'N/A'} | {row['title']}\n"
            f"  {row['description'][:100]}..."
        )
    return "\n\n".join(lines)


@mcp.tool()
def save_ticket(title: str, description: str, severity: str = "P3", service: str = "") -> str:
    """
    Guarda un nuevo ticket en la base de datos y devuelve su ID.
    A diferencia de create_ticket_draft (que solo genera texto),
    esta tool persiste el ticket para que otros puedan consultarlo.

    severity: P1 | P2 | P3 | P4
    service:  auth | database | api_gateway | frontend | (vacío si no aplica)
    """
    valid_severities = {"P1", "P2", "P3", "P4"}
    if severity not in valid_severities:
        severity = "P3"

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO tickets (title, description, severity, service, created_at) VALUES (?,?,?,?,?)",
        (title, description, severity, service or None, datetime.utcnow().isoformat()),
    )
    ticket_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return f"Ticket #{ticket_id} creado correctamente.\nTítulo: {title}\nSeveridad: {severity} — SLA: {_sla(severity)}"


@mcp.tool()
def close_ticket(ticket_id: int, resolution: str) -> str:
    """
    Cierra un ticket existente con la resolución aplicada.
    Devuelve error si el ticket no existe o ya está cerrado.
    """
    conn = get_db()
    row  = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

    if not row:
        conn.close()
        return f"Ticket #{ticket_id} no encontrado."

    if row["status"] == "closed":
        conn.close()
        return f"Ticket #{ticket_id} ya está cerrado."

    conn.execute(
        "UPDATE tickets SET status = 'closed', resolution = ?, closed_at = ? WHERE id = ?",
        (resolution, datetime.utcnow().isoformat(), ticket_id),
    )
    conn.commit()
    conn.close()

    return f"Ticket #{ticket_id} cerrado.\nResolución: {resolution}"


# ─────────────────────────────────────────────
# Arranque
# ─────────────────────────────────────────────

# Inicializar la BD antes de que el servidor empiece a aceptar conexiones.
# Si tickets.db no existe, se crea aquí con los datos de ejemplo.
init_db()

if __name__ == "__main__":
    # mcp.run() arranca el servidor con transporte stdio.
    # Bloquea hasta que el cliente cierra la conexión.
    # No hay output en consola — la comunicación es por stdin/stdout
    # en formato JSON-RPC, que es el protocolo que hay debajo de MCP.
    mcp.run()
