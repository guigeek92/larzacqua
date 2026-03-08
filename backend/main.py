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

from src.ai_extraction import ALLOWED_MODELS, RAGPipeline

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
        "allowed_models": ALLOWED_MODELS,
        "default_model": DEFAULT_MODEL,
        "schema_version": "1.1",
    }


@app.post("/extract", response_model=ExtractResponse)
async def extract_pdf(
    file: UploadFile = File(...),
    model: str | None = Form(default=None),
):
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF")

    # STEP 3 - Thread safety:
    # avoid a mutable global pipeline, instantiate per request/model.
    model_name = model or DEFAULT_MODEL
    if model_name not in ALLOWED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Modèle '{model_name}' non autorisé. Modèles valides : {', '.join(ALLOWED_MODELS)}",
        )

    started_at = perf_counter()
    try:
        pipeline = RAGPipeline(groq_model=model_name)
    except ValueError as err:
        # Usually caused by missing/invalid GROQ_API_KEY configuration.
        raise HTTPException(status_code=500, detail=str(err))

    try:
        content = await file.read()
        extraction = await run_in_threadpool(pipeline.extract_from_pdf, content)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:
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
