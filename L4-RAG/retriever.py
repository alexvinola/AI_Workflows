"""
L4 — RAG Retriever: busca los chunks más relevantes para una pregunta
=====================================================================
Segunda pieza del sistema RAG. Puede usarse de dos formas:

    1. Como script independiente (para probar que el retrieval funciona
       antes de conectar el LLM — muy útil para depurar).

    2. Importado por rag_pipeline.py:
       from retriever import retrieve

La función clave: `retrieve(query, top_k)` → lista de chunks ordenados
por relevancia semántica.

Requisito previo: ejecutar indexer.py al menos una vez.

Requisitos:
    pip install chromadb sentence-transformers
"""

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


# ─────────────────────────────────────────────
# Configuración — debe coincidir con indexer.py
# ─────────────────────────────────────────────

CHROMA_PATH     = "./chroma_db"
COLLECTION_NAME = "support_docs"

# CRÍTICO: usar exactamente el mismo modelo que se usó al indexar.
# Si cambias el modelo aquí sin reindexar, los vectores de la query
# y los vectores almacenados viven en espacios diferentes y la
# búsqueda no tiene sentido semántico.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

TOP_K_DEFAULT = 3  # cuántos chunks recuperar por defecto


# ─────────────────────────────────────────────
# Conexión a la colección (lazy, al primer uso)
# ─────────────────────────────────────────────

_collection = None

def _get_collection():
    """
    Abre la conexión a Chroma la primera vez que se necesita.
    Usar una variable global evita abrir la conexión múltiples
    veces si retrieve() se llama en un bucle.
    """
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        _collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_fn,
        )
    return _collection


# ─────────────────────────────────────────────
# Función principal de retrieval
# ─────────────────────────────────────────────

def retrieve(query: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    """
    Busca los chunks más relevantes para la pregunta dada.

    Proceso interno:
        1. Chroma calcula el embedding de `query` usando el mismo modelo
           que usamos al indexar (embedding_fn).
        2. Compara ese vector contra todos los vectores almacenados
           usando similitud coseno.
        3. Devuelve los top_k chunks con mayor similitud.

    Devuelve una lista de dicts con:
        - text:       el texto del chunk
        - source:     nombre del documento de origen
        - similarity: puntuación [0.0, 1.0] — cuánto se parece a la query
        - chunk_index: posición del chunk dentro del documento
    """
    collection = _get_collection()

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    # results["documents"][0]  → lista de textos (la [0] es porque query_texts acepta batch)
    # results["metadatas"][0]  → lista de metadatos
    # results["distances"][0]  → lista de distancias coseno [0, 2]
    #                            0 = idéntico, 2 = opuesto

    chunks = []
    docs      = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for text, meta, distance in zip(docs, metadatas, distances):
        # Convertimos distancia coseno a similitud [0, 1]
        # distancia=0 → similitud=1.0 (idéntico)
        # distancia=2 → similitud=0.0 (opuesto)
        similarity = 1.0 - (distance / 2.0)

        chunks.append({
            "text":        text,
            "source":      meta["source"],
            "chunk_index": meta["chunk_index"],
            "similarity":  round(similarity, 3),
        })

    return chunks


# ─────────────────────────────────────────────
# Uso como script (para probar el retrieval)
# ─────────────────────────────────────────────

def print_results(query: str, chunks: list[dict]) -> None:
    print(f"\nQuery: '{query}'")
    print("-" * 60)
    for i, chunk in enumerate(chunks, 1):
        print(f"\n[{i}] {chunk['source']} (chunk {chunk['chunk_index']}) — similitud: {chunk['similarity']:.1%}")
        print(chunk["text"][:300].replace("\n", " ") + "...")
    print()


# Preguntas de prueba para verificar que el retrieval funciona correctamente
# antes de conectar el LLM. Si los chunks recuperados no son relevantes,
# el LLM no va a poder responder bien — hay que arreglar el retrieval primero.
TEST_QUERIES = [
    "¿Qué hago cuando los usuarios no pueden hacer login?",
    "El servicio está devolviendo errores 500 en autenticación",
    "¿Cómo soluciono un problema de conexiones a la base de datos?",
    "Los clientes están recibiendo errores 429",
    "¿Qué pasa cuando el circuit breaker se abre?",
]

if __name__ == "__main__":
    print("=" * 60)
    print("PRUEBA DE RETRIEVAL — verificando que los chunks correctos")
    print("se recuperan antes de conectar el LLM")
    print("=" * 60)

    for query in TEST_QUERIES:
        chunks = retrieve(query)
        print_results(query, chunks)
