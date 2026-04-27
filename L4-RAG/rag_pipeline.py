"""
L4 — RAG Pipeline: recupera contexto y genera la respuesta con el LLM
======================================================================
Tercera y última pieza: une retrieval + generación.

Flujo completo de cada pregunta:
    Pregunta
        ↓
    retrieve()  →  chunks relevantes de la documentación
        ↓
    build_prompt()  →  prompt con contexto inyectado
        ↓
    Claude  →  respuesta fundamentada en los documentos reales
        ↓
    Respuesta + fuentes citadas

La diferencia clave con L2/L3: el LLM no responde desde su entrenamiento.
Responde desde los documentos que le pasamos en el contexto.
Si el retrieval falla, el modelo lo admite — no alucina una respuesta.

Requisitos:
    pip install anthropic chromadb sentence-transformers
    export ANTHROPIC_API_KEY="sk-ant-..."

Requisito previo: ejecutar indexer.py al menos una vez.
"""

import json
import anthropic
from retriever import retrieve

client = anthropic.Anthropic()
MODEL  = "claude-haiku-4-5-20251001"  # Haiku: rápido y barato para RAG. En RAG el
                                       # contexto lo provee el retrieval, no el modelo.


# ─────────────────────────────────────────────
# Construcción del prompt con contexto
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """
Eres un agente de soporte técnico especializado. Responde preguntas basándote
EXCLUSIVAMENTE en la documentación que se te proporciona en el contexto.

Reglas:
- Si la respuesta está en el contexto, respóndela citando la fuente entre corchetes: [nombre_doc.md]
- Si el contexto no contiene información suficiente para responder, dilo claramente:
  "La documentación disponible no cubre este caso."
- No uses tu conocimiento de entrenamiento para completar lo que falta en el contexto.
- Responde en español, de forma concisa y accionable.
""".strip()


def build_prompt(question: str, chunks: list[dict]) -> str:
    """
    Construye el mensaje de usuario con la pregunta y los chunks como contexto.

    El formato importa: separar claramente los chunks del contexto y la pregunta
    ayuda al modelo a distinguir entre "lo que debe usar" y "lo que debe responder".
    Cada chunk lleva su fuente para que el modelo pueda citarla.
    """
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"--- Fragmento {i} de {chunk['source']} ---\n{chunk['text']}"
        )

    context = "\n\n".join(context_parts)

    return f"""DOCUMENTACIÓN RELEVANTE:

{context}

---

PREGUNTA:
{question}"""


# ─────────────────────────────────────────────
# Pipeline principal
# ─────────────────────────────────────────────

def ask(question: str, top_k: int = 3, verbose: bool = True) -> dict:
    """
    Responde una pregunta usando RAG.

    Parámetros:
        question: la pregunta del usuario
        top_k:    cuántos chunks recuperar (más chunks = más contexto pero más tokens)
        verbose:  si True, muestra el proceso paso a paso

    Devuelve un dict con la respuesta y los metadatos del retrieval.
    """
    if verbose:
        print(f"\n{'=' * 60}")
        print(f"PREGUNTA: {question}")
        print(f"{'=' * 60}")

    # Paso 1: recuperar chunks relevantes
    chunks = retrieve(question, top_k=top_k)

    if verbose:
        print(f"\n[Retrieval] {len(chunks)} chunks recuperados:")
        for chunk in chunks:
            print(f"  • {chunk['source']} (chunk {chunk['chunk_index']}) — {chunk['similarity']:.1%}")

    # Paso 2: construir el prompt con el contexto inyectado
    user_message = build_prompt(question, chunks)

    # Paso 3: llamar al LLM con el contexto como parte del prompt
    # El modelo solo "ve" los chunks recuperados, no la documentación completa.
    # Esto es más eficiente (menos tokens) y más preciso (solo lo relevante).
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        temperature=0.1,  # casi determinista — es una pregunta con respuesta en el contexto
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    answer = response.content[0].text.strip()

    if verbose:
        print(f"\n[Respuesta]")
        print(answer)
        print(f"\n[Fuentes usadas]")
        sources = list({chunk["source"] for chunk in chunks})
        for src in sources:
            print(f"  • {src}")

    return {
        "question": question,
        "answer":   answer,
        "chunks":   chunks,
        "sources":  list({chunk["source"] for chunk in chunks}),
        "model":    MODEL,
    }


# ─────────────────────────────────────────────
# Ejemplos de uso
# ─────────────────────────────────────────────

# Preguntas diseñadas para cubrir los tres documentos y casos edge:
# - Preguntas directas (respuesta clara en la doc)
# - Pregunta fuera de cobertura (el modelo debe admitir que no sabe)

EXAMPLE_QUESTIONS = [
    # Documentado en authentication.md
    "¿Qué hago cuando el servicio de login devuelve errores 500?",

    # Documentado en database.md
    "Hay demasiadas conexiones a la base de datos y los servicios fallan. ¿Cómo lo soluciono?",

    # Documentado en api_gateway.md
    "Un cliente enterprise está recibiendo errores 429. ¿Por qué puede pasar eso?",

    # Requiere combinar auth + db
    "Los usuarios no pueden autenticarse y veo timeouts en los logs. ¿Por dónde empiezo?",

    # Fuera de la documentación disponible — el modelo debe decir que no sabe
    "¿Cómo configuro alertas de Prometheus para el servicio de pagos?",
]


if __name__ == "__main__":
    for question in EXAMPLE_QUESTIONS:
        result = ask(question)
        print()
