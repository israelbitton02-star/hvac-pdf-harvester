import logging
import os
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from collector import collect_pdfs
from models import CollectRequest, CollectResponse, DocumentRecord
from supabase_client import get_documents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="HVAC/PV PDF Harvester",
    version="1.0.0",
)

allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = ["*"] if allowed_origins_raw.strip() == "*" else [o.strip() for o in allowed_origins_raw.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/collect")
async def collect(request: CollectRequest):
    try:
        result = await collect_pdfs(request)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/documents")
async def list_documents():
    try:
        docs = await get_documents()
        return docs
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
