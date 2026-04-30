# L7 — MCP (Model Context Protocol)

## Qué es MCP

MCP es un protocolo de comunicación estándar que define cómo un LLM puede interactuar con sistemas externos. No es un almacén de contexto ni una librería — es un contrato, igual que REST define cómo se comunican aplicaciones web.

Antes de MCP, cada integración entre un modelo y un sistema externo era custom: tool use propio, formato propio, cliente propio. MCP estandariza eso. Cualquier cliente que hable MCP puede conectarse a cualquier servidor MCP — Claude, Cursor, o cualquier agente compatible.

## Arquitectura

MCP tiene tres componentes:

```
┌─────────────┐        MCP Protocol        ┌─────────────────┐
│  MCP Client │ ◄────────────────────────► │   MCP Server    │
│  (el LLM)   │                            │ (tu sistema)    │
└─────────────┘                            └─────────────────┘
```

**MCP Client** — el modelo o el agente que consume las capacidades. Claude, Cursor, o tu propio agente actúan como clientes.

**MCP Server** — el sistema que expone capacidades. Tú lo construyes. Puede ser un servidor que da acceso a repositorios, a una base de datos, a una API externa, o a cualquier fuente de información.

**MCP Protocol** — el contrato entre ambos. Define cómo el cliente descubre qué puede hacer el servidor, cómo hace las peticiones y cómo recibe los resultados.

## Qué puede exponer un MCP Server

Un servidor MCP puede exponer tres tipos de capacidades:

**Resources** — datos o contenido que el modelo puede leer. Equivalente a un GET en REST.
- El contenido de un archivo de un repositorio
- La documentación de un proyecto
- El resultado de una query a base de datos
- Los logs de un servicio

**Tools** — acciones que el modelo puede ejecutar. Equivalente a POST/PUT en REST.
- Crear un ticket en Jira
- Hacer un commit en un repositorio
- Enviar una notificación
- Ejecutar un script

**Prompts** — plantillas de prompts reutilizables que el servidor expone al cliente.
- "Analiza este PR siguiendo nuestros estándares de código"
- "Genera el release note de esta versión"

## El flujo completo

```
1. El cliente (LLM) se conecta al servidor MCP
2. El cliente descubre qué resources y tools están disponibles
3. El usuario hace una petición al LLM
4. El LLM decide qué resources leer o qué tools invocar
5. El servidor ejecuta la acción y devuelve el resultado
6. El LLM genera la respuesta con ese contexto
```

El paso 2 es clave: el cliente **descubre** las capacidades automáticamente. No tienes que hardcodear en el prompt qué tools existen — el servidor las describe y el cliente las entiende.

## Qué construimos en este nivel

Un MCP server en Python que expone acceso a documentación técnica:

- **`server.py`** — el servidor MCP con resources y tools
- **`client.py`** — un cliente de prueba que se conecta al servidor

El servidor expone:
- **Resource**: leer documentos de una carpeta local
- **Tool**: buscar en esa documentación por término
- **Tool**: crear un resumen de un documento

## Uso

```bash
pip install anthropic mcp
export ANTHROPIC_API_KEY="sk-ant-..."

# Terminal 1: arrancar el servidor
python server.py

# Terminal 2: conectar el cliente
python client.py
```

## MCP en el ecosistema real

MCP fue publicado por Anthropic en noviembre de 2024 y la adopción ha sido muy rápida. Hoy hay servidores MCP públicos para GitHub, GitLab, Jira, Linear, PostgreSQL, SQLite, Slack, Notion, Docker y Kubernetes entre otros.

Esto significa que en lugar de construir la integración desde cero, puedes conectar un servidor MCP existente y el modelo tiene acceso inmediato a esos sistemas.
