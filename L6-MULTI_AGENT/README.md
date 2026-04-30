# L6 — Multi-agente

## Qué es un sistema multi-agente

Un único agente trabaja en serie — investiga, decide, actúa, termina. Funciona bien para problemas que pueden resolverse de forma lineal. Cuando el problema es complejo y tiene partes independientes, el agente único tiene dos limitaciones:

**Velocidad**: un agente investiga la base de datos, luego la infraestructura, luego la seguridad — en secuencia. El tiempo total es la suma de cada investigación.

**Especialización**: un agente generalista que hace de todo tiene un system prompt cargado con contexto de múltiples dominios. Un especialista con un prompt enfocado es más preciso en su área.

Multi-agente resuelve ambas cosas: varios agentes especializados trabajan en paralelo, cada uno en su dominio, coordinados por un orquestador.

## La arquitectura orquestador / especialistas

```
                    Incidente
                       ↓
              ┌─── Orquestador ───┐
              │  Descompone el    │
              │  problema en      │
              │  subtareas        │
              └─────────┬─────────┘
                        │
          ┌─────────────┼─────────────┐
          ↓             ↓             ↓
   [Especialista   [Especialista  [Especialista
    Infraestructura]  Base de datos]  Aplicación]
          │             │             │
     sus tools     sus tools     sus tools
          │             │             │
          └─────────────┼─────────────┘
                        ↓
              ┌─── Orquestador ───┐
              │  Recibe informes  │
              │  Sintetiza        │
              │  Informe final    │
              └───────────────────┘
```

El orquestador no ejecuta herramientas — razona y coordina. Los especialistas no saben que hay otros agentes — solo reciben su tarea y la ejecutan.

## Las tres fases del orquestador

**Fase 1 — Descomposición**: el orquestador analiza el incidente y decide qué especialistas son necesarios y cuál es la tarea específica de cada uno. No siempre hacen falta todos.

**Fase 2 — Ejecución paralela**: los especialistas seleccionados corren simultáneamente. Cada uno es un agente L5 completo con su propio bucle de tools.

**Fase 3 — Síntesis**: el orquestador recibe los informes de todos los especialistas y produce el informe final, cruzando los hallazgos para encontrar la causa raíz.

## Por qué es L6 y no L5

En L5 hay un agente con seis tools que trabaja en serie. En L6:

| | L5 | L6 |
|---|---|---|
| Agentes | 1 generalista | 1 orquestador + N especialistas |
| Ejecución | Serie | Paralela |
| Context window | Un contexto con todo | Cada agente tiene su propio contexto limpio |
| Tiempo total | Suma de todas las investigaciones | Máximo de las investigaciones paralelas |
| Modelos | Uno | Pueden ser distintos según la tarea |

El último punto es importante: el orquestador usa un modelo más potente (necesita razonar sobre coordinación), los especialistas usan modelos más rápidos y baratos (tarea enfocada).

## Conceptos clave

### Paralelismo con asyncio

Los especialistas corren con `asyncio.gather()` — el equivalente Python de "lanza todo esto a la vez y espera a que termine lo último". Sin asyncio, el tiempo total sería la suma de todos los agentes. Con asyncio, es el tiempo del más lento.

```python
# Serie: 3 + 4 + 2 = 9 segundos
resultado_infra = await run_specialist("infra", ...)
resultado_db    = await run_specialist("database", ...)
resultado_app   = await run_specialist("app", ...)

# Paralelo: max(3, 4, 2) = 4 segundos
resultados = await asyncio.gather(
    run_specialist("infra", ...),
    run_specialist("database", ...),
    run_specialist("app", ...),
)
```

### Aislamiento de contexto

Cada especialista empieza con un contexto limpio — solo su tarea y sus tools. No sabe lo que están investigando los demás. Esto evita que el razonamiento de un agente contamine el de otro y mantiene cada contexto enfocado.

### Modelos distintos por rol

El orquestador usa `claude-sonnet-4-5` porque su trabajo requiere razonamiento sobre coordinación y síntesis de múltiples informes. Los especialistas usan `claude-haiku-4-5-20251001` porque tienen una tarea acotada y bien definida. Usar el modelo más caro para todo sería un desperdicio.

## Qué construimos en este nivel

- **`orchestrator.py`** — el sistema completo: orquestador + cuatro especialistas

Los especialistas son:
- **Infraestructura**: pods de Kubernetes, uso de recursos, conectividad de red
- **Base de datos**: conexiones activas, queries lentas, estado de la replicación
- **Aplicación**: logs del servicio, deploys recientes, tasa de errores
- **Seguridad**: intentos de autenticación fallidos, tráfico anómalo, cambios de permisos

## Uso

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

python orchestrator.py
```

## Siguientes pasos — L7

Con multi-agente el sistema puede atacar problemas complejos en paralelo. El siguiente nivel es **MCP**: en lugar de que cada integración sea custom, se estandariza cómo los agentes se comunican con sistemas externos — cualquier cliente compatible puede conectarse a cualquier servidor sin código adicional.
