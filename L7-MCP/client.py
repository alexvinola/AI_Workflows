"""
L7 — MCP Client: se conecta al servidor y usa Claude como agente
================================================================
El cliente tiene dos responsabilidades:

    1. Hablar con el servidor MCP — conectar, descubrir capacidades,
       ejecutar tools y leer resources.

    2. Actuar como puente entre Claude y el servidor — el LLM decide
       qué tools invocar, el cliente las ejecuta en el servidor y
       devuelve los resultados.

La SDK de MCP es asíncrona (asyncio), por eso todas las funciones
que hablan con el servidor son async/await.

Requisitos:
    pip install anthropic mcp
    export ANTHROPIC_API_KEY="sk-ant-..."

Uso:
    python client.py
    (arranca server.py automáticamente como subproceso)
"""

from dotenv import load_dotenv
load_dotenv()
import asyncio
import json
import anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


MODEL = "claude-haiku-4-5-20251001"

# StdioServerParameters le dice al cliente cómo arrancar el servidor.
# El cliente lanza `python server.py` como subproceso y se comunica
# con él por stdin/stdout — no hace falta arrancar el servidor a mano.
SERVER_PARAMS = StdioServerParameters(
    command="python",
    args=["server.py"],
)


# ─────────────────────────────────────────────
# Parte 1 — Discovery: qué expone el servidor
#
# Conectamos al servidor y listamos sus capacidades sin invocar
# ninguna lógica de LLM. Esto muestra el protocolo en sí:
# el cliente no sabe nada de antemano — todo lo descubre al conectar.
# ─────────────────────────────────────────────

async def discover(session: ClientSession) -> None:
    """Muestra qué resources y tools expone el servidor."""

    print("\n[Discovery] Resources disponibles:")
    resources = await session.list_resources()
    for r in resources.resources:
        print(f"  • {r.uri}  —  {r.description or r.name}")

    print("\n[Discovery] Tools disponibles:")
    tools = await session.list_tools()
    for t in tools.tools:
        params = list(t.inputSchema.get("properties", {}).keys())
        print(f"  • {t.name}({', '.join(params)})  —  {t.description}")


# ─────────────────────────────────────────────
# Parte 2 — Claude + MCP
#
# Las tools que descubrió el cliente se pasan a Claude.
# Cuando Claude decide invocar una, el cliente la ejecuta
# en el servidor MCP y devuelve el resultado.
# ─────────────────────────────────────────────

def mcp_tools_to_anthropic(tools) -> list[dict]:
    """
    Convierte las tools del formato MCP al formato que espera la API de Anthropic.
    MCP usa inputSchema (JSON Schema), Anthropic usa input_schema — mismo contenido,
    distinto nombre de campo.
    """
    return [
        {
            "name":         tool.name,
            "description":  tool.description or "",
            "input_schema": tool.inputSchema,
        }
        for tool in tools
    ]


async def ask(session: ClientSession, question: str) -> str:
    """
    Responde una pregunta usando Claude con acceso al servidor MCP.

    Flujo:
        1. Descubre las tools del servidor
        2. Pasa la pregunta + tools a Claude
        3. Si Claude llama una tool → la ejecuta en el servidor
        4. Devuelve el resultado al modelo y continúa
        5. Cuando Claude termina → devuelve la respuesta final
    """
    print(f"\n{'=' * 60}")
    print(f"PREGUNTA: {question}")
    print(f"{'=' * 60}")

    # Descubrir tools en cada llamada garantiza que siempre usamos
    # las capacidades actuales del servidor, aunque cambien en caliente
    tools_result     = await session.list_tools()
    anthropic_tools  = mcp_tools_to_anthropic(tools_result.tools)

    client   = anthropic.Anthropic()
    messages = [{"role": "user", "content": question}]

    # Bucle idéntico a L3 — la diferencia es que las tools no están
    # hardcodeadas en este fichero: vienen del servidor MCP
    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0,
            tools=anthropic_tools,
            messages=messages,
        )

        print(f"\n[Modelo] stop_reason: {response.stop_reason}")

        if response.stop_reason == "end_turn":
            answer = next(b.text for b in response.content if b.type == "text")
            print(f"\n[Respuesta]\n{answer}")
            return answer

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                print(f"\n[Tool] {block.name}({json.dumps(block.input, ensure_ascii=False)})")

                # El cliente ejecuta la tool en el servidor MCP.
                # Si mañana cambias la implementación de search_docs en server.py,
                # este código no cambia — solo cambia el servidor.
                result = await session.call_tool(block.name, block.input)

                # result.content es una lista de objetos de contenido;
                # para tools de texto tomamos el primero
                tool_output = result.content[0].text if result.content else ""
                print(f"[Tool result] {tool_output[:120]}...")

                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     tool_output,
                })

            messages.append({"role": "user", "content": tool_results})


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

async def main():
    # stdio_client arranca server.py como subproceso y gestiona
    # la conexión. Al salir del bloque `async with`, el subproceso
    # se termina limpiamente.
    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── Parte 1: ver qué expone el servidor ──
            print("=" * 60)
            print("DISCOVERY — capacidades del servidor MCP")
            print("=" * 60)
            await discover(session)

            # ── Parte 2: Claude usando el servidor ──
            print("\n\n" + "=" * 60)
            print("AGENTE — Claude con acceso al servidor MCP")
            print("=" * 60)

            questions = [
                # Busca en docs
                "¿Qué hago si el servicio de autenticación devuelve errores 500?",

                # Consulta la BD
                "¿Qué tickets críticos tenemos abiertos ahora mismo?",

                # Combina docs + BD: busca cómo resolverlo y cierra el ticket
                "El ticket #3 era el circuit breaker del API gateway. Ya lo hemos resuelto reiniciando Kong. Ciérralo.",

                # Crea ticket nuevo en la BD
                "Abre un ticket P2 para el servicio de base de datos: estamos viendo queries lentas en producción, "
                "algunas tardan más de 30 segundos.",
            ]

            for question in questions:
                await ask(session, question)
                print()


if __name__ == "__main__":
    asyncio.run(main())
