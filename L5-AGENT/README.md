# L5 — Agente

## Qué es un agente

Un agente es un modelo al que le das un **objetivo** y deja de esperar instrucciones paso a paso. Decide por sí solo qué herramientas usar, en qué orden, y cuándo ha terminado.

En los niveles anteriores siempre había un humano (o el código) controlando el flujo:
- L2: el programador define exactamente los pasos y su orden
- L3: el modelo elige qué tools invocar, pero responde a una pregunta concreta y puntual

En L5 el modelo recibe un objetivo abierto — *"investiga este incidente y resuélvelo"* — y trabaja de forma autónoma hasta completarlo.

## El bucle agente

```
┌─────────────────────────────────────────┐
│                                         │
│   Objetivo                              │
│      ↓                                  │
│   Observar  →  ¿qué sé hasta ahora?     │
│      ↓                                  │
│   Pensar    →  ¿qué debo hacer a cont.? │
│      ↓                                  │
│   Actuar    →  invocar tool             │
│      ↓                                  │
│   Evaluar   →  ¿he completado el obj.?  │
│      ↓ no                               │
│   (volver a Observar)                   │
│      ↓ sí                               │
│   Terminar  →  informe final            │
│                                         │
└─────────────────────────────────────────┘
```

La diferencia clave con L3 está en el **Evaluar**: en L3 el bucle termina cuando el modelo no necesita más tools. En L5 el bucle termina cuando el modelo decide que ha cumplido el objetivo — son condiciones de parada distintas.

## Por qué es L5 y no L3

En L3 la pregunta era puntual: *"clasifica este ticket"*. El modelo usaba dos tools, producía un JSON y terminaba. El objetivo era implícito y simple.

En L5 el objetivo es compuesto y abierto:

```
"Investiga este incidente. Determina la causa. Crea el ticket con la severidad
correcta. Si es P1 o P2, escala al equipo correspondiente. Redacta el informe final."
```

El modelo tiene que:
1. Decidir qué investigar primero basándose en el reporte inicial
2. Adaptar los siguientes pasos según lo que encuentre
3. Tomar acciones con efecto real (crear ticket, escalar)
4. Decidir activamente que el objetivo está cumplido

La autonomía no está en las tools — está en el razonamiento que guía cuándo y en qué orden usarlas, y en decidir cuándo parar.

## Conceptos clave

### Goal-directed behavior

El agente trabaja hacia un objetivo, no hacia una respuesta. La diferencia es sutil pero importante: una respuesta termina cuando el modelo dice algo. Un objetivo termina cuando el modelo *hace* algo — crear un ticket, escalar un incidente, notificar a un equipo.

### El system prompt como definición del agente

En L3 el system prompt describía el rol. En L5 describe el **protocolo de trabajo**: qué fases seguir, qué criterios usar para tomar decisiones, qué constituye "terminado". Es la diferencia entre *"eres un ingeniero de soporte"* y *"eres un ingeniero de soporte y este es tu proceso de trabajo"*.

### Autonomía y sus riesgos

Más autonomía significa más capacidad — y más superficie de error. Un agente puede:
- Encadenarse en un bucle si el objetivo no está bien definido
- Tomar decisiones incorrectas si las tools devuelven datos ambiguos
- Escalar innecesariamente si los criterios de severidad son vagos

Por eso el system prompt de un agente real invierte mucho más cuidado que el de una chain. Los criterios de decisión tienen que ser explícitos.

### Límite de iteraciones

En producción siempre se pone un techo al bucle — si el agente lleva N rondas sin terminar, algo ha ido mal. En este nivel el límite es `MAX_ITERATIONS = 10`. Si se alcanza, el agente para y reporta el estado parcial.

## Qué construimos en este nivel

Un agente autónomo de respuesta a incidentes:

- **`agent.py`** — el agente completo con su bucle, tools y lógica de terminación

El agente recibe un reporte de incidente en texto libre y de forma autónoma:
1. Investiga el estado actual de los servicios
2. Consulta el historial de incidentes similares
3. Busca el runbook de resolución
4. Crea el ticket con la severidad correcta
5. Escala si es necesario
6. Produce el informe final

## Uso

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

python agent.py
```

## Siguientes pasos — L6

Un agente solo resuelve problemas en serie — uno detrás de otro. Cuando los problemas son complejos y paralelizables, la solución es **multi-agente**: varios agentes especializados trabajando en paralelo, coordinados por un agente orquestador.
