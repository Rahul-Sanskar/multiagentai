"""
RAG routes
POST /api/v1/rag/ingest   — ingest a report into the pipeline
POST /api/v1/rag/query    — retrieve context chunks for a query
GET  /api/v1/rag/stats    — index stats
"""
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.rag_pipeline import RAGPipeline, RetrievedChunk

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

# single shared pipeline instance for the lifetime of the process
_rag = RAGPipeline()


class IngestRequest(BaseModel):
    report: dict[str, Any]
    source: str


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5
    source_filter: str | None = None


class ChunkOut(BaseModel):
    text: str
    source: str
    section: str
    score: float


@router.post("/ingest")
async def ingest(body: IngestRequest) -> dict[str, Any]:
    n = _rag.ingest(body.report, source=body.source)
    return {"chunks_added": n, "stats": _rag.stats()}


@router.post("/query", response_model=list[ChunkOut])
async def query(body: QueryRequest) -> list[RetrievedChunk]:
    if _rag.chunk_count == 0:
        raise HTTPException(status_code=400, detail="Index is empty — ingest a report first.")
    return _rag.retrieve_context(body.query, top_k=body.top_k, source_filter=body.source_filter)


@router.get("/stats")
async def stats() -> dict[str, Any]:
    return _rag.stats()
