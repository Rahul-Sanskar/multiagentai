"""
RAG Pipeline
------------
Ingests profile + competitor reports, chunks them, embeds with
sentence-transformers, stores in a local FAISS index, and exposes
retrieve_context(query) for semantic search.

All operations are local — no API calls.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────

_DEFAULT_MODEL = "all-MiniLM-L6-v2"   # 80 MB, fast, good quality
_CHUNK_SIZE = 120                       # words per chunk
_CHUNK_OVERLAP = 20                     # word overlap between chunks
_INDEX_PATH = Path("data/rag.index")
_CHUNKS_PATH = Path("data/rag_chunks.json")

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    text: str
    source: str          # e.g. "profile_report", "competitor_report"
    section: str         # e.g. "writing_style", "content_gaps"
    chunk_id: int = 0


@dataclass
class RetrievedChunk:
    text: str
    source: str
    section: str
    score: float         # cosine similarity (higher = more relevant)

# ── RAG Pipeline ──────────────────────────────────────────────────────────────

class RAGPipeline:
    """
    Lightweight local RAG pipeline backed by FAISS + sentence-transformers.

    Usage
    -----
    rag = RAGPipeline()
    rag.ingest(profile_report, source="profile_report")
    rag.ingest(competitor_report, source="competitor_report")
    results = rag.retrieve_context("what topics are trending?")
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self._model = SentenceTransformer(model_name)
        self._dim: int = self._model.get_sentence_embedding_dimension()
        self._index: faiss.IndexFlatIP | None = None   # inner-product on L2-normed vecs = cosine
        self._chunks: list[Chunk] = []

    # ── Ingestion ─────────────────────────────────────────────────────────

    def ingest(self, report: dict[str, Any], source: str) -> int:
        """
        Flatten a report dict into text chunks, embed them, and add to the index.
        Returns the number of chunks added.
        """
        raw_chunks = _flatten_report(report, source)
        if not raw_chunks:
            return 0

        texts = [c.text for c in raw_chunks]
        embeddings = self._embed(texts)

        if self._index is None:
            self._index = faiss.IndexFlatIP(self._dim)

        self._index.add(embeddings)

        # assign sequential ids
        start = len(self._chunks)
        for i, chunk in enumerate(raw_chunks):
            chunk.chunk_id = start + i

        self._chunks.extend(raw_chunks)
        return len(raw_chunks)

    def ingest_text(self, text: str, source: str, section: str = "raw") -> int:
        """Ingest a plain string directly (useful for ad-hoc additions)."""
        chunks = _chunk_text(text, source, section)
        return self.ingest_chunks(chunks)

    def ingest_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        texts = [c.text for c in chunks]
        embeddings = self._embed(texts)
        if self._index is None:
            self._index = faiss.IndexFlatIP(self._dim)
        self._index.add(embeddings)
        start = len(self._chunks)
        for i, c in enumerate(chunks):
            c.chunk_id = start + i
        self._chunks.extend(chunks)
        return len(chunks)

    # ── Retrieval ─────────────────────────────────────────────────────────

    def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        source_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Semantic search over the index.

        Parameters
        ----------
        query         : natural language question or keyword string
        top_k         : number of results to return
        source_filter : restrict results to a specific source label

        Returns
        -------
        List of RetrievedChunk sorted by relevance (highest first).
        """
        if self._index is None or not self._chunks:
            return []

        q_vec = self._embed([query])                    # (1, dim)
        k = min(top_k * 3, len(self._chunks))           # over-fetch for filtering
        scores, indices = self._index.search(q_vec, k)

        results: list[RetrievedChunk] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            if source_filter and chunk.source != source_filter:
                continue
            results.append(
                RetrievedChunk(
                    text=chunk.text,
                    source=chunk.source,
                    section=chunk.section,
                    score=float(round(score, 4)),
                )
            )
            if len(results) >= top_k:
                break

        return results

    # ── Persistence ───────────────────────────────────────────────────────

    def save(
        self,
        index_path: Path = _INDEX_PATH,
        chunks_path: Path = _CHUNKS_PATH,
    ) -> None:
        """Persist the FAISS index and chunk metadata to disk."""
        if self._index is None:
            raise RuntimeError("Nothing to save — index is empty.")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_path))
        chunks_path.write_text(
            json.dumps([c.__dict__ for c in self._chunks], indent=2),
            encoding="utf-8",
        )

    def load(
        self,
        index_path: Path = _INDEX_PATH,
        chunks_path: Path = _CHUNKS_PATH,
    ) -> None:
        """Load a previously saved index and chunk metadata from disk."""
        self._index = faiss.read_index(str(index_path))
        raw = json.loads(chunks_path.read_text(encoding="utf-8"))
        self._chunks = [Chunk(**c) for c in raw]

    # ── Stats ─────────────────────────────────────────────────────────────

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def stats(self) -> dict[str, Any]:
        sources: dict[str, int] = {}
        for c in self._chunks:
            sources[c.source] = sources.get(c.source, 0) + 1
        return {
            "total_chunks": self.chunk_count,
            "embedding_dim": self._dim,
            "sources": sources,
        }

    # ── Internal ──────────────────────────────────────────────────────────

    def _embed(self, texts: list[str]) -> np.ndarray:
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vecs.astype("float32")


# ── Text chunking helpers ─────────────────────────────────────────────────────

def _chunk_text(
    text: str,
    source: str,
    section: str,
    size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split text into overlapping word-window chunks."""
    words = text.split()
    chunks: list[Chunk] = []
    step = max(1, size - overlap)
    for i in range(0, len(words), step):
        window = words[i : i + size]
        if len(window) < 5:          # skip tiny trailing fragments
            break
        chunks.append(Chunk(text=" ".join(window), source=source, section=section))
    return chunks


def _flatten_report(report: dict[str, Any], source: str) -> list[Chunk]:
    """
    Recursively walk a report dict, convert leaf values to text,
    and chunk each section independently.
    """
    chunks: list[Chunk] = []

    def _walk(obj: Any, path: list[str]) -> None:
        section = ".".join(str(p) for p in path) if path else "root"
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, path + [k])
        elif isinstance(obj, list):
            # join list items into a single text blob for the section
            text = _list_to_text(obj)
            if text.strip():
                chunks.extend(_chunk_text(text, source, section))
        else:
            text = str(obj).strip()
            if text and text.lower() not in ("none", "null", ""):
                chunks.extend(_chunk_text(text, source, section))

    _walk(report, [])
    return chunks


def _list_to_text(items: list[Any]) -> str:
    parts = []
    for item in items:
        if isinstance(item, dict):
            parts.append(" ".join(f"{k}: {v}" for k, v in item.items()))
        else:
            parts.append(str(item))
    return ". ".join(parts)
