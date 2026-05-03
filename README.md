# AI Workflows

## Español

Llevo años trabajando como desarrollador Full Stack y desde el principio la IA ha formado parte de mi día a día — primero como herramienta, luego como área de interés real. En algún momento ese interés dejó de ser suficiente y quise entender qué hay detrás: cómo funcionan los modelos, cómo se diseñan los sistemas que los usan, y cómo se lleva todo eso a producción de forma seria.

Este repositorio documenta esa transición de forma pública y progresiva. No es un curso ni una guía — es mi proceso de aprendizaje real, con el código que escribo, los errores que cometo y los conceptos que voy consolidando.

### Estructura

El repo está organizado por niveles de sofisticación, siguiendo la escalera de workflows de IA. A mayor nivel, el modelo toma más decisiones por sí solo — y también aumenta la complejidad, el coste y la fragilidad. Cada nivel tiene su propia carpeta con un script autocontenido y un README que explica qué es, por qué funciona así y qué conceptos introduce.

| Nivel | Nombre                            | Descripción | Estado |
|-------|-----------------------------------|-------------|--------|
| L1 | [Prompt simple](./L1-SIMPLE/)     | Una instrucción, una respuesta. Sin estado ni herramientas. | Conocimiento previo |
| L2 | [Chain determinista](./L2-CHAIN/) | Pasos encadenados con flujo fijo definido por el programador | ✅ Completado |
| L3 | [Tool use](./L4-TOOL_USE/)        | El modelo decide cuándo invocar herramientas externas | ✅ Completado |
| L4 | [RAG](./L4-RAG/)                  | El modelo recupera contexto relevante antes de responder | ✅ Completado |
| L5 | [Agente](./L5-AGENT/)             | Bucle donde el modelo planifica, actúa y evalúa su progreso | ✅ Completado |
| L6 | [Multi-agente](./L6-MULTI_AGENT/) | Varios agentes especializados coordinados entre sí | ✅ Completado |
| L7 | [MCP](./L7-MCP/)                  | Protocolo estándar para exponer recursos y herramientas a cualquier cliente | ✅ Completado |

> El repo se irá actualizando a medida que avance en el aprendizaje.

---

## English

I have been working as a Full Stack developer for years, and AI has been part of my daily workflow from the start — first as a tool, then as a genuine area of interest. At some point that interest was no longer enough, and I wanted to understand what is underneath: how models work, how the systems that use them are designed, and how to bring all of that to production seriously.

This repository documents that transition publicly and progressively. It is not a course or a guide — it is my real learning process, with the code I write, the mistakes I make, and the concepts I consolidate along the way.

### Structure

The repo is organized by sophistication levels, following the AI workflow ladder. The higher the level, the more decisions the model makes on its own — and the higher the complexity, cost and fragility. Each level has its own folder with a self-contained script and a README that explains what it is, why it works that way, and what concepts it introduces.

| Level | Name                               | Description | Status |
|-------|------------------------------------|-------------|--------|
| L1 | [Simple prompt](./L1-SIMPLE/)      | One instruction, one response. No state or tools. | Prior knowledge |
| L2 | [Deterministic chain](./L2-CHAIN/) | Chained steps with fixed flow defined by the programmer | ✅ Done |
| L3 | [Tool use](./L3-TOOL_USE/)         | The model decides when to invoke external tools | ✅ Done |
| L4 | [RAG](./L4-RAG/)                   | The model retrieves relevant context before responding | ✅ Done |
| L5 | [Agent](./L5-AGENT/)               | Loop where the model plans, acts and evaluates its progress | ✅ Done |
| L6 | [Multi-agent](./L6-MULTI_AGENT/)   | Multiple specialized agents coordinated with each other | ✅ Done |
| L7 | [MCP](./L7-MCP/)                   | Standard protocol to expose resources and tools to any client | ✅ Done |

> The repo will be updated progressively as I advance in my learning.
