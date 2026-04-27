"""
Supabase client — stockage et base de données.

Utilise l'API REST Supabase directement via httpx pour éviter
les dépendances lourdes du client officiel Python.
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("supabase_client")

SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BUCKET = os.getenv("SUPABASE_BUCKET", "documents")
TABLE = "document_pdf"

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}

# Timeout généreux pour les uploads potentiellement lourds
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


# ── SHA256 helpers ────────────────────────────────────────────────────────────

def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── Deduplication ─────────────────────────────────────────────────────────────

async def sha256_exists(sha: str) -> bool:
    """Vérifie si un document avec ce sha256 existe déjà en base."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {
        "sha256": f"eq.{sha}",
        "select": "id",
        "limit": "1",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_HEADERS, params=params)
        resp.raise_for_status()
        return len(resp.json()) > 0


# ── Storage upload ────────────────────────────────────────────────────────────

async def upload_pdf(
    pdf_bytes: bytes,
    brand: str,
    model: str,
    sha: str,
    original_filename: str,
) -> tuple[str, str]:
    """
    Upload le PDF dans Supabase Storage.

    Retourne (storage_path, public_url).
    """
    safe_brand = brand.replace(" ", "_").lower()
    safe_model = model.replace(" ", "_").lower()
    safe_filename = original_filename.replace(" ", "_")
    storage_path = f"{safe_brand}/{safe_model}/{sha[:8]}_{safe_filename}"

    upload_url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{storage_path}"
    upload_headers = {
        **_HEADERS,
        "Content-Type": "application/pdf",
        "x-upsert": "false",
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(upload_url, headers=upload_headers, content=pdf_bytes)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"Storage upload failed [{resp.status_code}]: {resp.text[:300]}"
            )

    public_url = (
        f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{storage_path}"
    )
    logger.info("📤 Uploaded: %s", storage_path)
    return storage_path, public_url


# ── Database insert ───────────────────────────────────────────────────────────

async def insert_document(
    brand: str,
    model: str,
    title: str,
    doc_type: str,
    source_url: str,
    storage_path: str,
    storage_url: str,
    source: str,
    sha: str,
    file_size: int,
) -> dict:
    """Insère un enregistrement dans document_pdf et retourne la ligne créée."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    headers = {
        **_HEADERS,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {
        "brand": brand,
        "model": model,
        "title": title,
        "doc_type": doc_type,
        "source_url": source_url,
        "storage_path": storage_path,
        "storage_url": storage_url,
        "source": source,
        "sha256": sha,
        "file_size": file_size,
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else payload


# ── Document listing ──────────────────────────────────────────────────────────

async def get_documents() -> list[dict]:
    """Retourne tous les documents triés par created_at desc."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {
        "select": "*",
        "order": "created_at.desc",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(url, headers=_HEADERS, params=params)
        resp.raise_for_status()
        return resp.json()
