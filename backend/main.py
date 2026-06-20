from __future__ import annotations

import logging
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.ai_extraction import RAGPipeline

app = FastAPI(title="Energy AI Extraction API")


# STEP 1 - Backend observability:
# use structured logs instead of print() to keep traces usable in production/debug.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("energy-ai-tool.api")


# STEP 2 - API contract:
# explicit response model with a schema version, and a deprecated alias for backward compatibility.
class ExtractResponse(BaseModel):
    filename: str
    model_used: str
    schema_version: str = "1.1"
    document_type: str
    result_json: dict[str, Any]
    description: str = ""
    debug: dict[str, Any] = Field(default_factory=dict)
    # Deprecated alias kept temporarily so existing frontends keep working.
    result: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    question: str
    result_json: dict[str, Any]
    description: str = ""
    document_type: str | None = None
    model: str | None = None
    conversation: list[dict[str, str]] = Field(default_factory=list)
    analysis_context: str = ""


class ChatResponse(BaseModel):
    answer: str
    model_used: str

origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:8501",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_MODEL = "llama-3.1-8b-instant"


@app.get("/")
def read_root():
    return {
        "message": "Energy AI extraction API OK",
        "allowed_models": [DEFAULT_MODEL],
        "default_model": DEFAULT_MODEL,
        "schema_version": "1.1",
    }


@app.post("/extract", response_model=ExtractResponse)
async def extract_pdf(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
):
    if file.content_type not in {"text/csv", "application/csv"} and not (file.filename and file.filename.lower().endswith(".csv")):
        raise HTTPException(status_code=400, detail="Le fichier doit être un CSV classifié")

    # STEP 3 - Thread safety:
    # avoid a mutable global pipeline, instantiate per request/model.
    model_name = model or DEFAULT_MODEL
    # Suppression de la vérification ALLOWED_MODELS

    started_at = perf_counter()
    try:
        pipeline = RAGPipeline(groq_model=model_name)
    except ValueError as err:
        # Usually caused by missing/invalid GROQ_API_KEY configuration.
        raise HTTPException(status_code=500, detail=str(err))

    try:
        content = await file.read()
        extraction = await run_in_threadpool(pipeline.extract_from_csv, content, file.filename)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        import traceback
        logger.error(traceback.format_exc())
        logger.exception(
            "Extraction failure | file=%s | model=%s | error=%s",
            file.filename,
            model_name,
            err,
        )
        raise HTTPException(status_code=500, detail="Erreur serveur lors de l'extraction")

    duration_ms = int((perf_counter() - started_at) * 1000)
    logger.info(
        "Extraction success | file=%s | model=%s | doc_type=%s | duration_ms=%s",
        file.filename,
        model_name,
        extraction.get("document_type", "steu"),
        duration_ms,
    )

    result_json = extraction.get("json", {})

    return {
        "filename": file.filename,
        "model_used": model_name,
        "schema_version": "1.1",
        "document_type": extraction.get("document_type", "steu"),
        "result_json": result_json,
        # Backward compatibility field to avoid breaking existing clients.
        "result": result_json,
        "description": extraction.get("description", ""),
        "debug": extraction.get("debug", {}),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_with_extracted_data(payload: ChatRequest):
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide")

    model_name = payload.model or DEFAULT_MODEL
    # Suppression de la vérification ALLOWED_MODELS

    try:
        pipeline = RAGPipeline(groq_model=model_name)
    except ValueError as err:
        raise HTTPException(status_code=500, detail=str(err))

    started_at = perf_counter()
    try:
        answer = await run_in_threadpool(
            pipeline.answer_question_from_extracted_data,
            question,
            payload.result_json,
            payload.description,
            payload.document_type,
            payload.conversation,
            payload.analysis_context,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
        logger.exception(
            "Chat failure | model=%s | error=%s",
            model_name,
            err,
        )
        raise HTTPException(status_code=500, detail="Erreur serveur lors de la réponse chatbot")

    duration_ms = int((perf_counter() - started_at) * 1000)
    logger.info("Chat success | model=%s | duration_ms=%s", model_name, duration_ms)

    return {
        "answer": answer,
        "model_used": model_name,
    }
