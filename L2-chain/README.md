# L2 — Chain determinista

## Qué es L2

Varias llamadas al modelo encadenadas donde el programador controla el orden y el flujo, no el modelo. El modelo responde cuando se le llama — nunca decide qué paso ejecutar a continuación.

## Qué hace este script

Toma un ticket de soporte en texto libre y lo procesa en tres pasos:

```
Texto libre → [Paso 1] Extracción → [Paso 2] Clasificación → [Paso 3] Acción estructurada
```

El estado entre pasos lo gestionamos nosotros: `entities` y `classification` son variables Python normales que pasamos explícitamente al siguiente paso.

## Por qué es determinista

Dos razones:

**El flujo lo controla el código.** La secuencia está escrita en Python — siempre 1 → 2 → 3, sin excepciones. El modelo no puede saltarse pasos ni cambiar el orden.

**`temperature=0` en extracción y clasificación.** El mismo ticket siempre produce el mismo output. El paso 3 usa `temperature=0.2` porque es escritura de texto — un poco de variedad mejora la redacción.

## Conceptos clave

### Temperature

Controla la aleatoriedad del modelo al elegir la siguiente palabra. Técnicamente escala la distribución de probabilidad sobre todos los tokens posibles antes de muestrear.

| Valor | Comportamiento | Cuándo usarlo |
|-------|---------------|---------------|
| `0`   | Determinista, siempre el mismo output | Clasificación, extracción, parsing |
| `0.2` | Casi determinista, ligera variedad | Escritura técnica, resúmenes |
| `0.7+`| Creativo, variable | Brainstorming, copywriting |

### System prompt vs user prompt

- **System**: define el rol y las restricciones permanentes. No cambia entre llamadas.
- **User**: el input concreto de cada llamada — el ticket, las entidades, etc.

### Prompt injection

El equivalente del SQL injection para LLMs. Un usuario malicioso incluye instrucciones en su input intentando sobreescribir el system prompt.

Defensa usada en este script: envolver el input en etiquetas `[USER][/USER]` e indicar al modelo que ese contenido son datos, no instrucciones. Se complementa validando que el output sea JSON válido con el schema esperado.

## Uso

```bash
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."
python ticket_chain.py
```

## Siguientes pasos — L3

Una vez que la chain funciona, el siguiente nivel es **tool use**: en lugar de que el modelo clasifique solo con el contexto del prompt, puede invocar herramientas externas — consultar el historial de incidencias, verificar el estado del sistema en tiempo real, o buscar tickets similares.
