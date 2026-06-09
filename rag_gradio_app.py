"""Grounded generation and Gradio interface for the project 1 RAG app.

This module wires the retrieval stage to Groq's llama-3.3-70b-versatile model
and renders a small Gradio UI that returns:
- an answer generated only from retrieved context
- a programmatically constructed source list

The model is not trusted to add citations on its own. Source attribution is
derived from the retrieved chunk metadata after generation.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb
import gradio as gr
import numpy as np
from dotenv import load_dotenv
from groq import Groq
from sentence_transformers import SentenceTransformer


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = Path(os.getenv("CHROMA_PATH", BASE_DIR / "chroma_db"))
TOP_K = int(os.getenv("TOP_K", "5"))
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
CHROMA_COLLECTION_CANDIDATES = (
    os.getenv("CHROMA_COLLECTION_NAME") or "",
    "rag_chunks",
    "student_communities",
    "project1",
    "project_1",
    "documents",
)

SYSTEM_PROMPT = (
    "You are a retrieval-grounded assistant for a university student communities RAG system. "
    "Use only the information in the provided context. Do not use outside knowledge, guesses, "
    "or general background knowledge. "
    "Answer using whatever relevant information the context does contain, even if it only "
    "partially addresses the question or does not satisfy every qualifier (such as 'best' or "
    "'top'); in that case answer with what the context supports. "
    "If the context names relevant clubs, organizations, study groups, communities, or "
    "resources, list them as the answer. Do not refuse merely because the context does not "
    "rank them or does not use the exact wording of the question (for example, treat a "
    "relevant 'club' as a valid answer to a question about 'study groups'). "
    "Reply with exactly 'I don't have enough information on that.' only when the context "
    "contains no information relevant to the question. "
    "Keep the answer concise and factual. Do not mention sources, citations, chunk IDs, or "
    "the retrieval process because the app adds source attribution separately."
)


@dataclass(frozen=True)
class RetrievedChunk:
    source_label: str
    chunk_id: str
    text: str
    distance: float | None = None


def get_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing from the environment or .env file.")
    return Groq(api_key=api_key)


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def get_chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=str(CHROMA_PATH))


def existing_collection_names(client: chromadb.PersistentClient) -> list[str]:
    collections = client.list_collections()
    names: list[str] = []
    for collection in collections:
        names.append(getattr(collection, "name", str(collection)))
    return names


def choose_collection_name(client: chromadb.PersistentClient) -> str:
    available = existing_collection_names(client)
    for candidate in CHROMA_COLLECTION_CANDIDATES:
        if candidate and candidate in available:
            return candidate

    if len(available) == 1:
        return available[0]

    if available:
        raise RuntimeError(
            "Could not determine which Chroma collection to use. Available collections: "
            + ", ".join(available)
        )

    raise RuntimeError(
        f"No Chroma collections were found in {CHROMA_PATH}. Run the embedding/vector store step first."
    )


def get_collection() -> Any:
    client = get_chroma_client()
    collection_name = choose_collection_name(client)
    return client.get_collection(name=collection_name)


def normalize_embedding(vector: np.ndarray) -> list[float]:
    normalized = vector / np.linalg.norm(vector)
    return normalized.astype(float).tolist()


def embed_query(query: str) -> list[float]:
    embedding = get_embedder().encode(query, normalize_embeddings=True)
    if isinstance(embedding, np.ndarray):
        return embedding.astype(float).tolist()
    return list(map(float, embedding))


def get_source_label(metadata: dict[str, Any] | None, fallback_chunk_id: str) -> str:
    if not metadata:
        return fallback_chunk_id

    for key in ("source_name", "source", "filename", "file_name", "name"):
        value = metadata.get(key)
        if value:
            return str(value)

    return fallback_chunk_id


def retrieve_chunks(query: str, top_k: int = TOP_K) -> list[RetrievedChunk]:
    collection = get_collection()
    query_embedding = embed_query(query)
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        # "ids" is always returned and is rejected if listed in include (chromadb >= 1.x).
        include=["documents", "metadatas", "distances"],
    )

    documents = result.get("documents", [[]])[0] or []
    metadatas = result.get("metadatas", [[]])[0] or []
    distances = result.get("distances", [[]])[0] or []
    ids = result.get("ids", [[]])[0] or []

    retrieved: list[RetrievedChunk] = []
    for index, text in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else None
        chunk_id = str(ids[index]) if index < len(ids) and ids[index] else str(metadata.get("chunk_id")) if metadata else f"chunk_{index + 1}"
        source_label = get_source_label(metadata, chunk_id)
        distance = float(distances[index]) if index < len(distances) and distances[index] is not None else None
        retrieved.append(
            RetrievedChunk(
                source_label=source_label,
                chunk_id=chunk_id,
                text=str(text),
                distance=distance,
            )
        )

    return retrieved


def build_context(retrieved_chunks: list[RetrievedChunk]) -> str:
    if not retrieved_chunks:
        return ""

    sections: list[str] = []
    for index, chunk in enumerate(retrieved_chunks, start=1):
        sections.append(
            f"[Chunk {index}] Source: {chunk.source_label} | Chunk ID: {chunk.chunk_id}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(sections)


def build_user_prompt(question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
    context = build_context(retrieved_chunks)
    return (
        "Answer the question using only the information in the provided documents. "
        "Use whatever relevant information the documents contain, even if they only partially "
        "answer the question or do not satisfy every qualifier such as 'best' or 'top'. "
        "Say exactly 'I don't have enough information on that.' only when the documents contain "
        "nothing relevant to the question. "
        "Do not use outside knowledge. Do not mention sources or citations in your answer.\n\n"
        f"Question: {question}\n\n"
        f"Documents:\n{context}"
    )


def generate_answer(question: str, retrieved_chunks: list[RetrievedChunk]) -> str:
    if not retrieved_chunks:
        return "I don't have enough information on that."

    client = get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL_NAME,
        temperature=0.1,
        max_tokens=350,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(question, retrieved_chunks)},
        ],
    )

    content = response.choices[0].message.content or ""
    cleaned = content.strip()
    if not cleaned:
        return "I don't have enough information on that."
    return cleaned


def unique_source_labels(retrieved_chunks: list[RetrievedChunk]) -> list[str]:
    ordered_sources: OrderedDict[str, None] = OrderedDict()
    for chunk in retrieved_chunks:
        source = chunk.source_label.strip() or chunk.chunk_id
        ordered_sources.setdefault(source, None)
    return list(ordered_sources.keys())


def format_source_list(source_labels: list[str]) -> str:
    if not source_labels:
        return "No sources retrieved."

    lines = ["### Sources"]
    for label in source_labels:
        lines.append(f"- {label}")
    return "\n".join(lines)


def answer_question(question: str) -> tuple[str, str]:
    question = (question or "").strip()
    if not question:
        return "Enter a question to search the indexed documents.", "### Sources\n- No sources retrieved."

    try:
        retrieved_chunks = retrieve_chunks(question)
        answer = generate_answer(question, retrieved_chunks)
        sources_md = format_source_list(unique_source_labels(retrieved_chunks))
        return answer, sources_md
    except Exception as exc:  # noqa: BLE001 - surface runtime issues in the UI
        return f"Error: {exc}", "### Sources\n- No sources retrieved."


def build_app() -> gr.Blocks:
    with gr.Blocks(title="Student Communities RAG") as demo:
        gr.Markdown(
            "# Student Communities RAG\n"
            "Ask a question about university student communities or study groups.\n\n"
            "The model only sees retrieved context. Source attribution is added by the app, not by the model."
        )

        with gr.Row():
            question_box = gr.Textbox(
                label="Question",
                placeholder="Example: What are the best study groups for Computer Science students at UVM?",
                lines=3,
            )

        ask_button = gr.Button("Ask", variant="primary")

        gr.Markdown("## Answer")
        answer_box = gr.Markdown()
        gr.Markdown("## Sources")
        sources_box = gr.Markdown()

        ask_button.click(
            fn=answer_question,
            inputs=[question_box],
            outputs=[answer_box, sources_box],
        )
        question_box.submit(
            fn=answer_question,
            inputs=[question_box],
            outputs=[answer_box, sources_box],
        )

    return demo


def main() -> None:
    demo = build_app()
    demo.launch(theme=gr.themes.Soft())


if __name__ == "__main__":
    main()