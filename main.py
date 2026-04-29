import logging
import os
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from collector import collect_pdfs
from models import CollectRequest
from supabase_client import get_documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="HVAC/PV PDF Harvester", version="1.0.0")

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
async def collect(request: CollectRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(collect_pdfs, request)
    return {
        "status": "ok",
        "message": "Collecte lancée en arrière-plan",
        "products_processed": len(request.products),
        "pdfs_found": 0,
        "pdfs_uploaded": 0,
        "duplicates": 0,
        "errors": []
    }

@app.get("/documents")
async def list_documents():
    try:
        docs = await get_documents()
        return docs
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
