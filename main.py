import logging
import os
from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 PDF Harvester backend starting up")
    yield
    logger.info("🛑 PDF Harvester backend shutting down")


app = FastAPI(
    title="HVAC/PV PDF Harvester",
    description="Backend de collecte automatique de notices PDF HVAC et photovoltaïque",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = (
    ["*"]
    if allowed_origins_raw.strip() == "*"
    else [o.strip() for o in allowed_origins_raw.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["Monitoring"])
def health_check():
    """Vérifie que le backend est opérationnel."""
    return {"status": "ok"}


@app.post("/collect", response_model=CollectResponse, tags=["Collecte"])
async def collect(request: CollectRequest):
    """
    Lance la collecte de PDFs pour une liste de produits HVAC/PV.

    Pour chaque produit (marque + modèle), le backend :
    - génère plusieurs requêtes de recherche
    - extrait les URLs de PDFs
    - télécharge, déduplique (sha256)
    - uploade dans Supabase Storage
    - enregistre les métadonnées en base
    """
    logger.info(
        "📥 /collect called — %d product(s), max_results_per_query=%d",
        len(request.products),
        request.max_results_per_query,
    )
    try:
        result = await collect_pdfs(request)
        logger.info(
            "✅ /collect done — uploaded=%d duplicates=%d errors=%d",
            result.pdfs_uploaded,
            result.duplicates,
            len(result.errors),
        )
        return result
    except Exception as exc:
        logger.exception("💥 Unexpected error in /collect: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/documents", response_model=list[DocumentRecord], tags=["Documents"])
async def list_documents():
    """Retourne tous les PDFs indexés, triés par date de création décroissante."""
    try:
        docs = await get_documents()
        logger.info("📄 /documents — returned %d records", len(docs))
        return docs
    except Exception as exc:
        logger.exception("💥 Error in /documents: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
