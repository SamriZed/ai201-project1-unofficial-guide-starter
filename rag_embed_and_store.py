"""Embedding and vector-store build for the project 1 RAG corpus (Milestone 4).

This script bridges ingestion (rag_ingest_and_chunk.py) and the query app
(rag_gradio_app.py). It:
- Loads and chunks the local corpus with the existing ingestion functions
- Embeds every chunk with sentence-transformers all-MiniLM-L6-v2 (normalized)
- Stores chunk text, embeddings, and metadata (source_name, filename, chunk_id)
  in a persistent ChromaDB collection named "rag_chunks"

The collection name, embedding model, normalization, and metadata keys are kept
in sync with rag_gradio_app.py so retrieval works without extra configuration.
"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from rag_ingest_and_chunk import chunk_text, load_documents, tokenize


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", BASE_DIR / "chroma_db"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME", "rag_chunks")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
EMBED_BATCH_SIZE = 64


def build_records() -> tuple[list[str], list[str], list[dict[str, str]]]:
    """Chunk every loaded document, keeping each chunk tied to its source name."""

    documents = load_documents()
    if not documents:
        raise RuntimeError(
            "No documents loaded from documents/ or sources.txt. "
            "Run the ingestion step first."
        )

    ids: list[str] = []
    texts: list[str] = []
    metadatas: list[dict[str, str]] = []

    for document in documents:
        for chunk in chunk_text(document.cleaned_text, document.filename):
            ids.append(chunk.chunk_id)
            texts.append(chunk.text)
            metadatas.append(
                {
                    "source_name": document.source_name,
                    "filename": document.filename,
                    "chunk_id": chunk.chunk_id,
                }
            )

    if not texts:
        raise RuntimeError("Documents loaded but produced zero chunks after cleaning.")

    return ids, texts, metadatas


def embed_texts(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    embeddings = model.encode(
        texts,
        batch_size=EMBED_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    return embeddings.astype(float).tolist()


def reset_collection(client: chromadb.PersistentClient, name: str):
    """Drop any existing collection so re-runs do not duplicate chunks."""

    existing = {c.name for c in client.list_collections()}
    if name in existing:
        client.delete_collection(name)
    return client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def main() -> None:
    ids, texts, metadatas = build_records()
    print(f"Prepared {len(texts)} chunks from {len({m['filename'] for m in metadatas})} documents.")

    print(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    embeddings = embed_texts(model, texts)

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = reset_collection(client, CHROMA_COLLECTION_NAME)
    collection.add(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)

    token_counts = [len(tokenize(text)) for text in texts]
    print(f"Stored {collection.count()} chunks in collection '{CHROMA_COLLECTION_NAME}'.")
    print(f"Vector store path: {CHROMA_PATH}")
    print(
        "Chunk token stats: "
        f"min={min(token_counts)}, max={max(token_counts)}, "
        f"avg={sum(token_counts) / len(token_counts):.1f}"
    )

    # Smoke-test retrieval so a failed embed/store surfaces here, not in the UI.
    sample_query = "study groups for Computer Science students at UVM"
    probe = collection.query(
        query_embeddings=[model.encode(sample_query, normalize_embeddings=True).astype(float).tolist()],
        n_results=3,
        include=["metadatas", "distances"],
    )
    print(f"\nSmoke-test query: {sample_query!r}")
    for meta, dist in zip(probe["metadatas"][0], probe["distances"][0]):
        print(f"  - {meta.get('source_name')} ({meta.get('chunk_id')})  distance={dist:.3f}")


if __name__ == "__main__":
    main()
