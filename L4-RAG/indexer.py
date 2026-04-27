"""
L4 — RAG Indexer: divide documentos en chunks y los guarda en Chroma
====================================================================
Primera fase de RAG: la indexación.
Se ejecuta una vez (o cada vez que cambian los documentos).

Qué hace este script:
    1. Lee todos los .md de la carpeta docs/
    2. Divide cada documento en chunks con solapamiento
    3. Calcula el embedding de cada chunk (modelo local, sin API key)
    4. Guarda chunk + embedding + metadatos en ChromaDB

El resultado queda en ./chroma_db/ — una base de datos vectorial persistente
que retriever.py y rag_pipeline.py consultarán después.

Requisitos:
    pip install chromadb sentence-transformers

    No necesita API key — los embeddings se calculan en local con
    sentence-transformers. En el primer run descarga el modelo (~90 MB).
"""

import os
import glob
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction


# ─────────────────────────────────────────────
# Configuración
# ─────────────────────────────────────────────

DOCS_PATH       = "./docs"
CHROMA_PATH     = "./chroma_db"
COLLECTION_NAME = "support_docs"

# all-MiniLM-L6-v2: modelo pequeño (90 MB), rápido, buena calidad para búsqueda semántica.
# Este mismo modelo HAY QUE USARLO también en retriever.py — si indexas con A y
# buscas con B, los vectores son incompatibles y los resultados serán basura.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

CHUNK_SIZE    = 500   # caracteres por chunk
CHUNK_OVERLAP = 100   # caracteres de solapamiento entre chunks consecutivos


# ─────────────────────────────────────────────
# Chunking
# ─────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """
    Divide el texto en chunks de tamaño fijo con solapamiento.

    Por qué solapamiento: si una idea importante cae justo en el límite
    entre dos chunks, el solapamiento garantiza que aparece completa
    en al menos uno de ellos y no queda cortada.

    Ejemplo con chunk_size=10, overlap=3:
        texto:  "abcdefghijklmnopqrst"
        chunk1: "abcdefghij"           (start=0)
        chunk2: "hijklmnopq"           (start=7)  ← 'hij' se repite
        chunk3: "nopqrst"              (start=14)
    """
    chunks = []
    start  = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        # Avanzamos (chunk_size - overlap) para que el siguiente chunk
        # empiece overlap caracteres antes del final del actual
        start += chunk_size - overlap
    return chunks


# ─────────────────────────────────────────────
# Carga de documentos
# ─────────────────────────────────────────────

def load_documents(docs_path: str) -> list[dict]:
    """
    Lee todos los archivos .md de la carpeta y devuelve una lista de dicts
    con el contenido y el nombre del fichero como fuente.

    Guardamos el nombre del fichero como metadato para poder decirle al
    usuario de dónde viene cada respuesta — esto es lo que llaman "citations"
    o "source attribution" en sistemas RAG de producción.
    """
    documents = []
    pattern   = os.path.join(docs_path, "*.md")

    for filepath in sorted(glob.glob(pattern)):
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        documents.append({"source": filename, "content": content})
        print(f"  Cargado: {filename} ({len(content)} caracteres)")

    return documents


# ─────────────────────────────────────────────
# Indexación
# ─────────────────────────────────────────────

def index_documents(documents: list[dict], collection) -> int:
    """
    Divide cada documento en chunks y los añade a la colección de Chroma.

    Cada chunk se almacena con:
        - document: el texto del chunk (lo que se buscará)
        - embedding: el vector calculado por embedding_fn (Chroma lo hace automáticamente)
        - metadata: fuente y número de chunk (para atribución y depuración)
        - id: identificador único — Chroma lo requiere para evitar duplicados
    """
    total_chunks = 0

    for doc in documents:
        chunks = chunk_text(doc["content"])
        source = doc["source"]

        print(f"\n  {source}: {len(chunks)} chunks")

        ids       = []
        texts     = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{source}__chunk_{i}"
            ids.append(chunk_id)
            texts.append(chunk)
            metadatas.append({"source": source, "chunk_index": i})

            # Mostramos los primeros 60 chars para ver qué se indexa
            preview = chunk[:60].replace("\n", " ")
            print(f"    [{i}] {preview}...")

        # Chroma llama a embedding_fn internamente para cada texto
        # y almacena el resultado junto al texto y los metadatos
        collection.add(documents=texts, metadatas=metadatas, ids=ids)
        total_chunks += len(chunks)

    return total_chunks


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("FASE 1 — INDEXACIÓN")
    print("=" * 60)

    # PersistentClient guarda los datos en disco.
    # La próxima vez que lo abras (retriever.py, rag_pipeline.py)
    # los embeddings ya están calculados — no hay que recalcularlos.
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)

    # get_or_create_collection: si ya existe (de una indexación anterior), la borramos
    # y recreamos para que los cambios en los docs se reflejen.
    # En producción se usaría una estrategia de actualización incremental.
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"\nColección anterior eliminada — reindexando desde cero.")
    except Exception:
        pass  # no existía, no hay problema

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        # cosine: mide similitud de dirección entre vectores (independiente de la magnitud)
        # Es la métrica más usada para comparar embeddings de texto
        metadata={"hnsw:space": "cosine"},
    )

    print(f"\nCargando documentos desde '{DOCS_PATH}'...")
    documents = load_documents(DOCS_PATH)

    if not documents:
        print(f"\nERROR: No se encontraron archivos .md en '{DOCS_PATH}'")
        return

    print(f"\nIndexando {len(documents)} documentos...")
    total = index_documents(documents, collection)

    print(f"\n{'=' * 60}")
    print(f"Indexación completada: {total} chunks en '{CHROMA_PATH}'")
    print(f"Modelo de embeddings: {EMBEDDING_MODEL}")
    print(f"Chunk size: {CHUNK_SIZE} chars | Overlap: {CHUNK_OVERLAP} chars")
    print(f"{'=' * 60}")
    print("\nAhora puedes ejecutar:")
    print("  python retriever.py         ← probar el retrieval")
    print("  python rag_pipeline.py      ← RAG completo con LLM")


if __name__ == "__main__":
    main()
