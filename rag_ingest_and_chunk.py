"""Offline ingestion and chunking for the project 1 RAG corpus.

This script follows the planning spec for the project:
- Read the source order from planning.md
- Load local extracted text only, never live websites
- Clean HTML tags, entities, extra whitespace, and boilerplate
- Chunk into approximately 300–500 tokens with 50-token overlap
- Store metadata for filename and chunk id
- Print one cleaned document, five sample chunks, the total chunk count, and
    chunk statistics
"""

from __future__ import annotations

import html
import random
import re
import statistics
import textwrap
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


PLANNING_FILE = Path(__file__).with_name("planning.md")
DOCUMENTS_DIR = Path(__file__).with_name("documents")
LOCAL_CORPUS_FILE = Path(__file__).with_name("sources.txt")
TARGET_CHUNK_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 50
RANDOM_SAMPLE_SEED = 42


@dataclass
class SourceDocument:
    source_name: str
    filename: str
    cleaned_text: str
    raw_text: str = ""


@dataclass
class Chunk:
    filename: str
    chunk_id: str
    text: str


class VisibleTextExtractor(HTMLParser):
    """Extract visible text while ignoring common boilerplate tags."""

    BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "tr",
    }
    SKIP_TAGS = {"script", "style", "svg", "noscript", "iframe", "form", "button"}

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 - HTMLParser API
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)


def parse_sources_from_planning(planning_path: Path) -> list[dict[str, str]]:
    """Parse the source table from planning.md.

    The planning file contains both "Documents" and "Document Sources" tables.
    We collect rows from either table and keep entries that have a URL.
    """

    content = planning_path.read_text(encoding="utf-8")
    sources: list[dict[str, str]] = []
    in_table = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("| # | Source |") or stripped.startswith("| # | Source | Type |"):
            in_table = True
            continue
        if in_table and not stripped.startswith("|"):
            in_table = False
        if not in_table or stripped.startswith("|---"):
            continue

        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue

        source_name = cells[1]
        description = cells[2]
        url = cells[3]
        if url.startswith("http://") or url.startswith("https://"):
            sources.append({"source_name": source_name, "description": description, "url": url})

    return sources


def derive_filename(source_name: str, fallback_index: int) -> str:
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name).strip("._")
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "_", candidate).strip("._")
    if not candidate:
        candidate = f"source_{fallback_index}"
    return candidate


def natural_sort_key(path: Path) -> list[object]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def discover_local_text_files() -> list[Path]:
    if not DOCUMENTS_DIR.exists():
        return []
    return sorted(
        [path for path in DOCUMENTS_DIR.glob("*.txt") if path.is_file()],
        key=natural_sort_key,
    )


def split_corpus_sections(corpus_text: str) -> list[str]:
    section_pattern = re.compile(
        r"^\s*(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+source:\s*$",
        re.IGNORECASE,
    )
    sections: list[list[str]] = []
    current_lines: list[str] = []

    for line in corpus_text.splitlines():
        if section_pattern.match(line):
            if current_lines:
                sections.append(current_lines)
            current_lines = []
            continue
        current_lines.append(line)

    if current_lines:
        sections.append(current_lines)

    return ["\n".join(lines).strip() for lines in sections if "\n".join(lines).strip()]


def load_local_corpus_file(corpus_file: Path) -> list[SourceDocument]:
    planning_sources = parse_sources_from_planning(PLANNING_FILE)
    corpus_text = corpus_file.read_text(encoding="utf-8", errors="replace")
    sections = split_corpus_sections(corpus_text)

    documents: list[SourceDocument] = []
    for index, section_text in enumerate(sections, start=1):
        if index <= len(planning_sources):
            source_name = planning_sources[index - 1]["source_name"]
        else:
            source_name = f"Source {index}"
        documents.append(
            SourceDocument(
                source_name=source_name,
                filename=derive_filename(source_name, index),
                cleaned_text=clean_text(section_text),
                raw_text=section_text,
            )
        )

    return documents


def extract_visible_text(raw_text: str) -> str:
    parser = VisibleTextExtractor()
    parser.feed(raw_text)
    parser.close()
    return parser.get_text()


def clean_text(text: str) -> str:
    """Remove tags, entities, extra whitespace, and obvious boilerplate lines."""

    if "<" in text and ">" in text:
        text = extract_visible_text(text)

    text = html.unescape(text)
    text = text.replace("\r", "\n")
    lines: list[str] = []

    boilerplate_patterns = [
        r"^skip to (main|content)$",
        r"^accept all cookies$",
        r"^cookie(s)? (policy|preferences)$",
        r"^privacy policy$",
        r"^terms of service$",
        r"^all rights reserved$",
        r"^table of contents$",
        r"^testimonials$",
        r"^all categories$",
        r"^club$",
        r"^search$",
        r"^graduate$",
        r"^undergraduate$",
        r"^graduate/undergraduate$",
        r"^staff/faculty/administrators$",
        r"^sign in$",
        r"^log in$",
        r"^log out$",
        r"^menu$",
        r"^share$",
    ]

    metadata_prefixes = (
        "advisor:",
        "category:",
        "email:",
        "social media:",
        "website:",
        "user image",
        "updated ",
        "save",
        "menu",
        "search",
        "search student organization by",
    )

    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue

        normalized = line.lower()
        if any(re.match(pattern, normalized) for pattern in boilerplate_patterns):
            continue

        if normalized.startswith(metadata_prefixes):
            continue

        if re.search(r"\b(advisor|email|category|social media|website):", normalized):
            continue

        if len(normalized.split()) == 1 and len(normalized) <= 3:
            continue

        if len(normalized.split()) <= 3 and normalized.isalpha() and normalized.isupper():
            continue

        lines.append(line)

    cleaned = " ".join(lines)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def detokenize(tokens: Iterable[str]) -> str:
    return " ".join(tokens)


def chunk_text(
    text: str,
    filename: str,
    chunk_size_tokens: int = TARGET_CHUNK_TOKENS,
    overlap_tokens: int = CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    tokens = tokenize(text)
    if not tokens:
        return []

    if chunk_size_tokens <= overlap_tokens:
        raise ValueError("chunk_size_tokens must be larger than overlap_tokens")

    step = chunk_size_tokens - overlap_tokens
    chunks: list[Chunk] = []

    for start in range(0, len(tokens), step):
        end = min(start + chunk_size_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        if not chunk_tokens:
            break

        chunk_id = f"{filename}::chunk_{len(chunks) + 1:03d}"
        chunks.append(Chunk(filename=filename, chunk_id=chunk_id, text=detokenize(chunk_tokens)))

        if end >= len(tokens):
            break

    return chunks


def load_documents() -> list[SourceDocument]:
    planning_sources = parse_sources_from_planning(PLANNING_FILE)
    local_files = discover_local_text_files()

    if local_files:
        documents: list[SourceDocument] = []
        for index, path in enumerate(local_files, start=1):
            if index <= len(planning_sources):
                source_name = planning_sources[index - 1]["source_name"]
            else:
                source_name = path.stem
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            documents.append(
                SourceDocument(
                    source_name=source_name,
                    filename=path.name,
                    raw_text=raw_text,
                    cleaned_text=clean_text(raw_text),
                )
            )
        return documents

    if LOCAL_CORPUS_FILE.exists():
        documents = load_local_corpus_file(LOCAL_CORPUS_FILE)
        if documents:
            return documents

    return []


def build_all_chunks(documents: Iterable[SourceDocument]) -> list[Chunk]:
    all_chunks: list[Chunk] = []
    for document in documents:
        all_chunks.extend(chunk_text(document.cleaned_text, document.filename))
    return all_chunks


def preview(text: str, limit: int = 450) -> str:
    return textwrap.shorten(text, width=limit, placeholder="...")


def chunk_statistics(chunks: Iterable[Chunk]) -> tuple[int, int, float]:
    token_counts = [len(tokenize(chunk.text)) for chunk in chunks]
    if not token_counts:
        return 0, 0, 0.0
    return min(token_counts), max(token_counts), statistics.mean(token_counts)


def print_cleaned_document(document: SourceDocument) -> None:
    print("CLEANED DOCUMENT")
    print(f"Filename: {document.filename}")
    print(f"Source: {document.source_name}")
    print(preview(document.cleaned_text, limit=1000))
    print()


def print_sample_chunks(chunks: list[Chunk], sample_size: int = 5) -> None:
    print("SAMPLE CHUNKS")
    if not chunks:
        print("No chunks available.")
        print()
        return

    rng = random.Random(RANDOM_SAMPLE_SEED)
    sample = chunks if len(chunks) <= sample_size else rng.sample(chunks, sample_size)
    for chunk in sample:
        print(f"- filename={chunk.filename} | chunk_id={chunk.chunk_id} | tokens={len(tokenize(chunk.text))}")
        print(f"  {preview(chunk.text)}")
    print()


def print_chunk_summary(chunks: list[Chunk]) -> None:
    min_tokens, max_tokens, avg_tokens = chunk_statistics(chunks)
    print(f"TOTAL CHUNKS: {len(chunks)}")
    print(f"CHUNK STATISTICS: min={min_tokens}, max={max_tokens}, average={avg_tokens:.2f}")


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No local documents could be loaded from documents/ or sources.txt.")
        return

    all_chunks = build_all_chunks(documents)

    print_cleaned_document(documents[0])
    print_sample_chunks(all_chunks, sample_size=5)
    print_chunk_summary(all_chunks)


if __name__ == "__main__":
    main()