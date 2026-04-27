# L4 — RAG (Retrieval-Augmented Generation)

## Qué es RAG

Un LLM sabe mucho — pero solo lo que aprendió durante su entrenamiento. No sabe nada de tu documentación interna, de los tickets de tu empresa, del estado de tu sistema hoy, ni de nada que haya ocurrido después de su fecha de corte.

RAG resuelve eso: en lugar de pedirle al modelo que "recuerde" información que no tiene, se la buscamos nosotros y se la metemos en el contexto justo antes de que responda.

```
Sin RAG: Pregunta → LLM → Respuesta (basada solo en entrenamiento)
Con RAG: Pregunta → Buscar documentos relevantes → Pregunta + Contexto → LLM → Respuesta
```

## Los dos conceptos nuevos

### Embedding

Un embedding es una representación numérica del **significado** de un texto. Concretamente, una lista de números (un vector) donde cada número captura algún aspecto semántico del texto.

```
"El servicio de login está caído"  → [0.23, -0.87, 0.41, 0.12, ...]  (1536 números)
"Users cannot authenticate"        → [0.24, -0.85, 0.39, 0.11, ...]  (muy similar)
"El tiempo en Zaragoza mañana"     → [0.91,  0.12, -0.67, 0.88, ...] (muy diferente)
```

La propiedad clave: **textos con significado similar producen vectores similares**, aunque usen palabras completamente distintas. Esto permite buscar por significado en lugar de por palabras exactas.

Un modelo de embeddings (como `text-embedding-3-small` de OpenAI o `nomic-embed-text`) es un modelo diferente al LLM — su único trabajo es convertir texto en vectores. No genera texto, no responde preguntas, solo transforma.

### Base de datos vectorial

Una base de datos diseñada para almacenar vectores y buscar los más similares a uno dado de forma eficiente. La similitud se mide con distancia matemática entre vectores — los más cercanos son los más similares en significado.

La búsqueda vectorial es fundamentalmente diferente a SQL:

| SQL | Base de datos vectorial |
|-----|------------------------|
| `WHERE texto LIKE '%login%'` | "Dame los chunks más similares a esta pregunta" |
| Busca palabras exactas | Busca significado semántico |
| Rápido en texto exacto | Rápido en similitud aproximada |
| No entiende sinónimos | Entiende sinónimos y paráfrasis |

Opciones populares: **pgvector** (extensión de PostgreSQL, fácil si ya usas Postgres), **Qdrant** (open source, muy usado en producción), **Chroma** (ideal para aprender, sin infraestructura), **Pinecone** (managed, sin servidor).

En este nivel usamos **Chroma** porque corre en local sin configuración.

## Las dos fases de RAG

RAG tiene dos fases completamente separadas que ocurren en momentos distintos:

### Fase 1 — Indexación (se hace una vez o periódicamente)

```
Documentos
    ↓
Dividir en chunks (trozos de ~500 palabras con algo de solapamiento)
    ↓
Calcular el embedding de cada chunk (llamada al modelo de embeddings)
    ↓
Guardar chunk + embedding en la base de datos vectorial
```

El **solapamiento entre chunks** es importante: si un chunk termina en medio de una frase y el siguiente empieza en la siguiente, puedes perder contexto. Con solapamiento de 50-100 palabras te aseguras de que ninguna idea queda partida entre dos chunks.

### Fase 2 — Consulta (se hace en cada pregunta)

```
Pregunta del usuario
    ↓
Calcular el embedding de la pregunta (mismo modelo de embeddings)
    ↓
Buscar los N chunks más similares en la base de datos vectorial
    ↓
Construir el prompt: pregunta + chunks recuperados como contexto
    ↓
LLM genera la respuesta basándose en ese contexto
```

## Por qué es L4 y no L2 o L3

En L2 el flujo lo controlaba el código. En L3 el modelo decidía cuándo usar tools. En L4 la complejidad es diferente: hay **infraestructura** (la base de datos vectorial), un **modelo adicional** (el de embeddings), y un pipeline que ocurre en dos momentos distintos (indexación y consulta).

Además, la calidad del RAG depende de decisiones de diseño que no hay en niveles anteriores: tamaño de los chunks, cantidad de solapamiento, cuántos chunks recuperar, cómo construir el prompt con el contexto.

## Qué construimos en este nivel

Un sistema RAG sobre documentación de soporte técnico:

1. **`indexer.py`** — lee documentos, los divide en chunks, calcula embeddings y los guarda en Chroma
2. **`retriever.py`** — dado una pregunta, recupera los chunks más relevantes
3. **`rag_pipeline.py`** — une todo: recupera contexto y genera la respuesta con el LLM

## Conceptos adicionales

### Chunking strategy

La forma de dividir los documentos afecta directamente la calidad del retrieval. Las estrategias más comunes:

- **Fixed size**: chunks de N caracteres con solapamiento. Simple y funciona bien en la mayoría de casos.
- **Recursive**: divide por párrafos, luego por frases, luego por palabras hasta llegar al tamaño objetivo. Respeta mejor la estructura del texto.
- **Semantic**: usa embeddings para dividir donde cambia el tema. Más costoso pero más preciso.

En este nivel usamos fixed size con solapamiento — es el punto de partida correcto.

### Top-K retrieval

Cuando buscas en la base de datos vectorial, recuperas los K chunks más similares. K es un parámetro que ajustas: demasiado bajo y te falta contexto, demasiado alto y metes ruido en el prompt (y gastas más tokens).

En la práctica K=3 o K=5 es un buen punto de partida.

### Sentence Transformers

`sentence-transformers` es la librería Python que usamos para calcular embeddings en local. Envuelve modelos de Hugging Face y los expone con una interfaz simple:

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
vector = model.encode("El servicio de login está caído")  # → array de 384 números
```

El modelo `all-MiniLM-L6-v2` es un buen punto de partida: pesa ~90 MB, corre en CPU sin problemas y tiene buena calidad para búsqueda semántica en la mayoría de dominios. Se descarga automáticamente desde Hugging Face la primera vez que lo usas.

Una restricción importante: **el modelo de embeddings tiene que ser el mismo en indexación y en consulta**. Si indexas con `all-MiniLM-L6-v2` y luego buscas con otro modelo, los vectores viven en espacios matemáticos diferentes y los resultados no tienen sentido semántico. Si cambias el modelo, hay que reindexar desde cero.

En este nivel usamos `sentence-transformers` a través de ChromaDB, que lo integra directamente con `SentenceTransformerEmbeddingFunction`. Para usar un modelo diferente basta con cambiar la constante `EMBEDDING_MODEL` en `indexer.py` y `retriever.py` (y reindexar).

### Hallucination vs grounding

Sin RAG el modelo puede "alucinar" — generar información plausible pero incorrecta porque no tiene la fuente real. Con RAG el modelo tiene el documento real en el contexto, lo que reduce drásticamente las alucinaciones — siempre que el retrieval haya encontrado los chunks correctos.

Si el retrieval falla (no encuentra los chunks relevantes), el modelo responde con lo que sabe de entrenamiento o admite que no tiene información. Por eso la calidad del retrieval es tan crítica.

## Uso

```bash
pip install anthropic chromadb sentence-transformers
export ANTHROPIC_API_KEY="sk-ant-..."

# Paso 1: indexar los documentos
python indexer.py

# Paso 2: lanzar consultas
python rag_pipeline.py
```

## Cómo sería esto en producción

Lo que construimos aquí son tres scripts que corren en tu máquina. En producción cada
pieza se convierte en un servicio independiente. Este apartado explica qué cambiaría
y cómo se conectaría todo.

### Arquitectura general

```
                        ┌─────────────────────────────────────────┐
                        │           PIPELINE DE INDEXACIÓN         │
                        │              (asíncrono)                 │
                        │                                          │
  Confluence/Notion ────►                                          │
  S3 / Google Drive ────► Worker de indexación ──► Modelo de      │
  Base de datos     ────►   (indexer.py)            embeddings    │
                        │         │                 (HF / local)  │
                        │         ▼                               │
                        │   Base de datos vectorial               │
                        │   (pgvector en PostgreSQL)              │
                        └─────────────┬───────────────────────────┘
                                      │
                                      │ lee en cada consulta
                                      │
                        ┌─────────────▼───────────────────────────┐
                        │           PIPELINE DE CONSULTA           │
                        │              (tiempo real)               │
                        │                                          │
  Usuario ──► UI web ──► API (FastAPI) ──► Retrieval              │
                        │                      │                  │
                        │                      ▼                  │
                        │              Modelo de embeddings        │
                        │              (misma instancia)          │
                        │                      │                  │
                        │                      ▼                  │
                        │              Top-K chunks               │
                        │                      │                  │
                        │                      ▼                  │
                        │              Claude API (LLM)           │
                        │                      │                  │
  Usuario ◄── UI web ◄── API ◄──── Respuesta + fuentes           │
                        └─────────────────────────────────────────┘
```

### Los dos pipelines separados

**Pipeline de indexación** — corre en background, no en tiempo real

En producción los documentos cambian constantemente: alguien actualiza un runbook,
se añade una nueva página en Confluence, se cierra un incidente y se documenta.
La indexación no puede ser un script manual — tiene que ser automática.

Las dos estrategias más comunes:

- **Event-driven**: cada vez que se crea o modifica un documento, se dispara un evento
  (webhook, mensaje en una cola SQS/Kafka) que lanza la reindexación de ese documento.
  Latencia baja, complejidad media.
- **Batch periódico**: un cron job que cada noche re-indexa todos los documentos
  modificados en las últimas 24 horas. Más simple, con hasta un día de desfase.

**Pipeline de consulta** — corre en tiempo real, en cada petición del usuario

Aquí el usuario espera una respuesta. La latencia importa. Las operaciones son:
1. Calcular el embedding de la pregunta (~10-50ms con un modelo en GPU)
2. Búsqueda vectorial (~5-20ms con pgvector en una tabla bien indexada)
3. Llamada al LLM (~500ms-2s según el modelo y la longitud de la respuesta)

El cuello de botella siempre es el LLM. El retrieval es rápido.

### Los componentes de infraestructura

| Componente | En este proyecto | En producción |
|---|---|---|
| Base de datos vectorial | ChromaDB (fichero local) | pgvector (PostgreSQL) o Qdrant |
| Modelo de embeddings | Local via sentence-transformers | Desplegado en HF Endpoint o instancia propia |
| LLM | Claude API | Claude API (igual) |
| API | No existe | FastAPI / Django |
| Cola de indexación | No existe | SQS, Celery, o similar |
| Caché | No existe | Redis (respuestas frecuentes) |
| Frontend | No existe | Web app, Slack bot, o widget |

**¿Por qué pgvector en vez de Chroma?** Porque en producción ya tienes PostgreSQL.
Añadir pgvector es `CREATE EXTENSION vector` — no es una base de datos nueva que operar,
monitorizar y pagar por separado. Chroma es perfecto para aprender; pgvector es lo que
usarías si mañana lo pusieras en un servidor real.

### Cómo llegaría la pregunta del usuario al modelo

El flujo concreto de una petición real:

```
1. El usuario escribe en la UI: "¿Cómo reinicio el servicio de auth?"

2. La UI hace POST /api/ask  { "question": "..." }

3. La API recibe la petición y llama al pipeline de retrieval:
     embedding = modelo_embeddings.encode(question)          # vector de la pregunta
     chunks = pgvector.query(embedding, top_k=3)             # búsqueda semántica

4. La API construye el prompt con los chunks como contexto y llama a Claude:
     response = anthropic.messages.create(
         model="claude-haiku-...",
         system="Responde basándote en el contexto proporcionado...",
         messages=[{ "role": "user", "content": contexto + pregunta }]
     )

5. La API devuelve:
     { "answer": "...", "sources": ["authentication.md"] }

6. La UI muestra la respuesta con las fuentes enlazadas al documento original.
```

### El modelo de embeddings en producción

En este proyecto sentence-transformers descarga `all-MiniLM-L6-v2` a tu máquina y lo
corre localmente. En producción tienes dos opciones:

**Opción A — Mismo modelo, desplegado como servicio interno**

El modelo corre en una instancia dedicada (CPU o GPU) y la API lo llama por HTTP.
Ventaja: barato, sin dependencia externa, el modelo no cambia nunca por sorpresa.

```
API ──► POST http://embedding-service/encode  { "text": "..." }
     ◄── { "vector": [0.23, -0.87, ...] }
```

**Opción B — API de embeddings externa**

Usar un proveedor como OpenAI (`text-embedding-3-small`) o el Inference Endpoint de
Hugging Face. Más simple de operar, pero añade latencia de red, coste por token,
y dependencia de un tercero.

Para la mayoría de casos, la opción A con `all-MiniLM-L6-v2` en una instancia pequeña
es suficiente y más barato. Solo merece la pena la opción B si necesitas un modelo
de mayor calidad para un dominio muy específico.

### Caché de respuestas

En producción muchos usuarios hacen las mismas preguntas. Calcular el embedding,
buscar en pgvector y llamar al LLM para "¿cómo reinicio el auth service?" la décima
vez es un desperdicio. La solución habitual es Redis:

```
Pregunta entra
    ↓
¿Está en caché Redis?  ──Sí──► Devolver respuesta cacheada (< 1ms)
    ↓ No
Ejecutar RAG completo
    ↓
Guardar en Redis con TTL de 1 hora
    ↓
Devolver respuesta
```

La clave del caché no es el texto exacto de la pregunta sino su embedding —
así "cómo reinicio auth" y "restart del servicio de autenticación" dan el mismo
resultado cacheado aunque usen palabras distintas.

## Siguientes pasos — L5

Con RAG el sistema puede responder sobre documentación estática. El siguiente nivel son los **agentes**: sistemas que combinan RAG, tool use y memoria para razonar sobre objetivos complejos de forma autónoma, decidiendo por sí mismos qué pasos dar y en qué orden.