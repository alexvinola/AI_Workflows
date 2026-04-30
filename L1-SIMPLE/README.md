# L1 — Single LLM Call

## Qué es L1

Una llamada a un modelo de lenguaje: le mandas texto, te devuelve texto.

No hay lógica, no hay herramientas, no hay memoria. Solo una petición y una respuesta. Es el bloque más pequeño con el que está construido todo lo demás — chains, agentes, RAG — son combinaciones y extensiones de esta operación básica.

## La anatomía de una petición

Cuando llamas a un LLM via API mandas un objeto con estos campos:

```
model       → qué modelo usar
max_tokens  → cuántos tokens puede generar como máximo en la respuesta
temperature → cuánta aleatoriedad tiene la respuesta (0 = determinista, 1 = creativo)
system      → instrucciones permanentes que definen el rol y el comportamiento del modelo
messages    → el historial de la conversación: quién dijo qué
```

```json
{
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 256,
  "temperature": 0,
  "system": "Eres un asistente de soporte técnico. Responde de forma concisa.",
  "messages": [
    { "role": "user", "content": "¿Qué significa un error 503?" }
  ]
}
```

## La anatomía de una respuesta

El modelo devuelve:

```
content      → lista de bloques de contenido (normalmente uno de texto)
stop_reason  → por qué paró de generar: "end_turn" (terminó), "max_tokens" (se cortó)
usage        → cuántos tokens consumió: input_tokens + output_tokens
```

```json
{
  "content": [
    { "type": "text", "text": "Un 503 Service Unavailable significa que el servidor..." }
  ],
  "stop_reason": "end_turn",
  "usage": { "input_tokens": 32, "output_tokens": 41 }
}
```

## Conceptos clave

### Tokens

El modelo no lee palabras — lee tokens. Un token es aproximadamente una sílaba o una palabra corta en inglés. En español suele ser algo más por palabra por la morfología del idioma.

```
"El servicio está caído"  →  6 tokens aproximadamente
"authentication"          →  3-4 tokens
```

Los tokens importan por dos razones: determinan el coste (se cobra por token) y el límite de lo que cabe en una conversación (el context window).

### Context window

El espacio total que tiene el modelo para leer y generar. Todo cuenta: el system prompt, el historial de mensajes, y la respuesta que va a generar. Si la conversación supera ese límite, hay que truncar o resumir el historial.

Los modelos modernos tienen context windows de cientos de miles de tokens — suficiente para conversaciones largas o documentos completos.

### System prompt vs user prompt

Son dos canales distintos con propósitos distintos:

| | System | User |
|---|---|---|
| **Quién lo escribe** | El desarrollador | El usuario (o el código) |
| **Cuándo cambia** | Nunca (o raramente) | En cada mensaje |
| **Para qué sirve** | Definir el rol, las reglas, el formato de respuesta | El input concreto de cada interacción |

El system prompt es el contrato permanente con el modelo. El user prompt es lo que varía.

### Temperature

Controla cómo de predecible es la respuesta del modelo al elegir la siguiente palabra.

| Valor | Comportamiento | Cuándo usarlo |
|-------|---------------|---------------|
| `0` | Siempre la respuesta más probable — determinista | Clasificación, extracción, parsing |
| `0.2 – 0.5` | Casi determinista, ligera variedad | Resúmenes, escritura técnica |
| `0.7+` | Creativo, variable | Brainstorming, generación de ideas |

Para tareas donde hay una respuesta correcta, `temperature=0`. Para tareas creativas, más alto.

## Por qué no hay código en L1

Una llamada directa al modelo no requiere arquitectura — cualquier lenguaje con soporte HTTP puede hacerla. El aprendizaje de L1 está en entender qué es un token, cómo funciona el context window, y qué diferencia hay entre system y user prompt.

Estos conceptos son los que luego explican por qué L2 (chains) funciona como funciona, por qué en L3 (tool use) hay un bucle, y por qué en L4 (RAG) metemos contexto en el prompt en lugar de esperar que el modelo "lo sepa".

## El flujo más simple posible

```
Developer define system prompt
        ↓
Usuario escribe un mensaje
        ↓
API recibe: model + system + messages
        ↓
Modelo genera tokens uno a uno hasta end_turn o max_tokens
        ↓
Respuesta llega como texto
```

## Siguientes pasos — L2

Una llamada aislada no tiene memoria ni estado — el modelo no recuerda lo que dijiste en el mensaje anterior a menos que lo incluyas en el historial. El siguiente nivel, L2, encadena varias llamadas pasando el output de una como input de la siguiente, con el código controlando el flujo.
