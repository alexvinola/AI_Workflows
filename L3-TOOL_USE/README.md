# L3 — Tool use

## Qué es L3

En L2 el modelo trabaja ciego: solo sabe lo que le pasas en el prompt. En L3 le das acceso a **herramientas** — funciones que puede invocar para obtener información externa o ejecutar acciones.

La diferencia fundamental con L2: el modelo participa en el flujo. Tú defines las herramientas disponibles, pero él decide cuándo usarlas y con qué parámetros.

## Cómo funciona

El ciclo de una llamada con tool use tiene cuatro pasos:

```
1. Tú defines las tools disponibles y envías el mensaje
2. El modelo decide si necesita una tool y devuelve una tool_use (no texto)
3. Tú ejecutas la función real con los parámetros que dio el modelo
4. Devuelves el resultado al modelo y él genera la respuesta final
```

El modelo **nunca ejecuta código directamente**. Dice "quiero llamar a `search_similar_tickets` con `query='auth 500 error'`" — y tú ejecutas esa llamada real y le devuelves el resultado. El control de seguridad siempre está en tu código.

## Por qué importa esto

En L2 el clasificador de severidad tomaba decisiones basándose solo en el texto del ticket y en lo que el modelo sabe por su entrenamiento. Eso tiene un límite claro: el modelo no sabe si ese componente ha fallado antes, si hay una incidencia activa ahora mismo, ni cómo se resolvieron casos similares.

Con tool use el modelo puede consultar esa información antes de clasificar — y la respuesta es cualitativamente mejor porque está basada en datos reales, no en inferencias.

## Diferencia con L2

| | L2 — Chain | L3 — Tool use |
|--|------------|---------------|
| Flujo | Lo controla el código siempre | El modelo decide si invocar tools |
| Información disponible | Solo lo que está en el prompt | Puede consultar sistemas externos |
| Determinismo | Alto — siempre los mismos pasos | Medio — el modelo elige qué tools usar |
| Complejidad | Baja | Media |

## Conceptos clave

### Tool definition

Antes de la llamada le describes al modelo las tools disponibles: nombre, descripción y parámetros con sus tipos. El modelo usa esa descripción para decidir cuándo y cómo invocarlas — por eso la descripción importa tanto como el código.

```python
tools = [
    {
        "name": "search_similar_tickets",
        "description": "Busca tickets de soporte similares resueltos anteriormente. Úsala cuando necesites contexto histórico sobre un problema.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Descripción breve del problema a buscar"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados (default: 3)"
                }
            },
            "required": ["query"]
        }
    }
]
```

### Tool use block

Cuando el modelo decide invocar una tool, no devuelve texto — devuelve un bloque de tipo `tool_use` con el nombre de la función y los parámetros que quiere usar:

```json
{
  "type": "tool_use",
  "name": "search_similar_tickets",
  "input": {
    "query": "authentication service 500 error",
    "max_results": 3
  }
}
```

Tú recibes esto, ejecutas la función real, y devuelves el resultado en el siguiente turno de la conversación.

### Tool result

El resultado de la tool vuelve al modelo como un mensaje de tipo `tool_result`. El modelo lo lee y decide si necesita más tools o si ya tiene suficiente información para responder.

```python
messages.append({
    "role": "user",
    "content": [
        {
            "type": "tool_result",
            "tool_use_id": tool_use_block.id,
            "content": json.dumps(result)
        }
    ]
})
```

### Stop reason

En L2 el modelo siempre terminaba con `stop_reason: "end_turn"`. En L3 puede terminar con `stop_reason: "tool_use"` — significa que quiere invocar una tool y está esperando el resultado. Tu código tiene que manejar ambos casos.

## Qué construimos en este nivel

Un clasificador de tickets mejorado respecto a L2, con dos tools disponibles:

- `search_similar_tickets` — busca tickets parecidos resueltos anteriormente
- `get_system_status` — consulta el estado actual de los servicios

Ambas son mocks — devuelven datos simulados. El concepto es la arquitectura: cuando tengas la integración real con Jira o tu sistema de monitorización, solo cambias la implementación de la tool, no el resto del sistema.

## Uso

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python ticket_classifier.py
```

## Siguientes pasos — L4

Con tool use el modelo puede consultar información externa. El siguiente nivel añade **memoria y estado persistente**: el modelo recuerda conversaciones anteriores, aprende del historial y puede razonar sobre el contexto acumulado a lo largo del tiempo.