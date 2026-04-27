"""
collector.py — Moteur de collecte de PDFs.

Pipeline pour chaque produit :
  1. Génération des requêtes de recherche
  2. Recherche web via DuckDuckGo (ddgs)
  3. Extraction des URLs de PDFs
  4. Téléchargement + vérification content-type
  5. Calcul SHA256 + déduplication
  6. Upload Supabase Storage
  7. Insertion Supabase Postgres
"""

import asyncio
import logging
import re
import urllib.parse
from pathlib import PurePosixPath
from typing import Optional

import httpx
from duckduckgo_search import DDGS

from models import CollectRequest, CollectResponse, ProductQuery
from supabase_client import (
    insert_document,
    sha256_exists,
    sha256_of_bytes,
    upload_pdf,
)

logger = logging.getLogger("collector")

# ── Configuration ─────────────────────────────────────────────────────────────

# Templates de requêtes de recherche par produit
QUERY_TEMPLATES = [
    "{brand} {model} notice pdf",
    "{brand} {model} installation pdf",
    "{brand} {model} manuel pdf",
    "{brand} {model} maintenance pdf",
]

# Types de doc déduits du template
QUERY_DOC_TYPES = {
    "notice": "notice",
    "installation": "installation",
    "manuel": "manuel",
    "maintenance": "maintenance",
}

MAX_PDF_SIZE_MB = 50
MAX_PDF_SIZE_BYTES = MAX_PDF_SIZE_MB * 1024 * 1024

_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_SEARCH_PAUSE = 1.5  # secondes entre requêtes DDG (éviter le rate-limit)

# User-agent neutre pour les téléchargements
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; HVACDocBot/1.0; "
        "+https://github.com/your-org/hvac-pdf-harvester)"
    )
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_type_from_query(query_template: str) -> str:
    for keyword, dtype in QUERY_DOC_TYPES.items():
        if keyword in query_template:
            return dtype
    return "document"


def _filename_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        name = PurePosixPath(parsed.path).name
        return name if name.lower().endswith(".pdf") else "document.pdf"
    except Exception:
        return "document.pdf"


def _title_from_url(url: str, brand: str, model: str) -> str:
    name = _filename_from_url(url)
    stem = PurePosixPath(name).stem.replace("_", " ").replace("-", " ")
    return stem if stem else f"{brand} {model}"


def _extract_pdf_urls_from_results(results: list[dict]) -> list[str]:
    """Extrait les URLs pointant vers des PDFs depuis les résultats DDG."""
    urls = []
    for r in results:
        href = r.get("href", "") or r.get("url", "")
        if not href:
            continue
        # URL directe vers un PDF
        if href.lower().endswith(".pdf") or "pdf" in href.lower():
            urls.append(href)
        # Cherche dans le body du résultat des liens PDF imbriqués
        body = r.get("body", "")
        if body:
            found = re.findall(r'https?://[^\s"\'<>]+\.pdf', body, re.IGNORECASE)
            urls.extend(found)
    # Dédupliquer tout en préservant l'ordre
    seen: set[str] = set()
    unique = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


async def _search_pdf_urls(
    brand: str, model: str, template: str, max_results: int
) -> list[tuple[str, str]]:
    """
    Lance une recherche DDG et retourne une liste de (url, doc_type).
    Bloquant via run_in_executor pour ne pas bloquer la boucle async.
    """
    query = template.format(brand=brand, model=model)
    doc_type = _doc_type_from_query(template)
    logger.info("🔍 Searching: %s", query)

    def _sync_search():
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as exc:
            logger.warning("DDG search failed for '%s': %s", query, exc)
            return []

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _sync_search)
    urls = _extract_pdf_urls_from_results(results)
    logger.info("  → %d PDF URL(s) found for query '%s'", len(urls), query)
    return [(url, doc_type) for url in urls]


async def _download_pdf(url: str) -> Optional[bytes]:
    """
    Télécharge un PDF et vérifie le content-type.
    Retourne les bytes ou None en cas d'échec.
    """
    try:
        async with httpx.AsyncClient(
            timeout=_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            headers=_HEADERS,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                logger.warning(
                    "⚠️  Non-PDF content-type '%s' for %s — skipping",
                    content_type,
                    url[:80],
                )
                return None

            data = resp.content
            if len(data) > MAX_PDF_SIZE_BYTES:
                logger.warning(
                    "⚠️  PDF too large (%.1f MB) — skipping %s",
                    len(data) / 1024 / 1024,
                    url[:80],
                )
                return None

            # Vérification magic bytes PDF (%PDF-)
            if not data.startswith(b"%PDF"):
                logger.warning("⚠️  File doesn't start with %%PDF — skipping %s", url[:80])
                return None

            logger.info(
                "⬇️  Downloaded %.1f KB from %s",
                len(data) / 1024,
                url[:80],
            )
            return data

    except httpx.HTTPStatusError as exc:
        logger.warning("HTTP %d for %s", exc.response.status_code, url[:80])
        return None
    except Exception as exc:
        logger.warning("Download error for %s: %s", url[:80], exc)
        return None


# ── Main collect function ─────────────────────────────────────────────────────

async def collect_pdfs(request: CollectRequest) -> CollectResponse:
    errors: list[str] = []
    pdfs_found = 0
    pdfs_uploaded = 0
    duplicates = 0

    for product in request.products:
        brand = product.brand.strip()
        model = product.model.strip()
        logger.info("🏭 Processing product: %s %s", brand, model)

        # Collecter toutes les URLs candidates pour ce produit
        candidate_pairs: list[tuple[str, str]] = []  # (url, doc_type)
        for template in QUERY_TEMPLATES:
            pairs = await _search_pdf_urls(
                brand, model, template, request.max_results_per_query
            )
            candidate_pairs.extend(pairs)
            await asyncio.sleep(_SEARCH_PAUSE)

        # Dédupliquer les URLs avant téléchargement
        seen_urls: set[str] = set()
        unique_pairs = []
        for url, dtype in candidate_pairs:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_pairs.append((url, dtype))

        logger.info(
            "  %d unique PDF URL(s) to process for %s %s",
            len(unique_pairs),
            brand,
            model,
        )

        for url, doc_type in unique_pairs:
            pdfs_found += 1

            # Téléchargement
            pdf_bytes = await _download_pdf(url)
            if pdf_bytes is None:
                errors.append(f"Download failed: {url[:100]}")
                continue

            # SHA256 + déduplication en base
            sha = sha256_of_bytes(pdf_bytes)
            try:
                exists = await sha256_exists(sha)
            except Exception as exc:
                logger.error("DB check error: %s", exc)
                errors.append(f"DB error checking sha256: {exc}")
                continue

            if exists:
                logger.info("♻️  Duplicate (sha256 already in DB): %s", url[:80])
                duplicates += 1
                continue

            # Upload Supabase Storage
            filename = _filename_from_url(url)
            title = _title_from_url(url, brand, model)
            try:
                storage_path, storage_url = await upload_pdf(
                    pdf_bytes, brand, model, sha, filename
                )
            except Exception as exc:
                logger.error("Upload error for %s: %s", url[:80], exc)
                errors.append(f"Upload error [{url[:80]}]: {exc}")
                continue

            # Insertion en base
            try:
                await insert_document(
                    brand=brand,
                    model=model,
                    title=title,
                    doc_type=doc_type,
                    source_url=url,
                    storage_path=storage_path,
                    storage_url=storage_url,
                    source="duckduckgo",
                    sha=sha,
                    file_size=len(pdf_bytes),
                )
                pdfs_uploaded += 1
                logger.info("✅ Indexed: %s / %s — %s", brand, model, title)
            except Exception as exc:
                logger.error("DB insert error: %s", exc)
                errors.append(f"DB insert error: {exc}")

    return CollectResponse(
        status="ok",
        products_processed=len(request.products),
        pdfs_found=pdfs_found,
        pdfs_uploaded=pdfs_uploaded,
        duplicates=duplicates,
        errors=errors,
    )
