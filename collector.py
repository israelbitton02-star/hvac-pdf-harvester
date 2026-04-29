import asyncio
import logging
import re
import urllib.parse
from pathlib import PurePosixPath
from typing import Optional
import os

import httpx

from models import CollectRequest, CollectResponse
from supabase_client import (
    insert_document,
    sha256_exists,
    sha256_of_bytes,
    upload_pdf,
)

logger = logging.getLogger("collector")

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")

QUERY_TEMPLATES = [
    "{brand} {model} notice pdf",
    "{brand} {model} installation pdf",
    "{brand} {model} manuel pdf",
    "{brand} {model} maintenance pdf",
]

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024
_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HVACDocBot/1.0)"}


def _doc_type_from_query(query: str) -> str:
    for keyword in ["notice", "installation", "manuel", "maintenance"]:
        if keyword in query:
            return keyword
    return "document"


def _filename_from_url(url: str) -> str:
    try:
        name = PurePosixPath(urllib.parse.urlparse(url).path).name
        return name if name.lower().endswith(".pdf") else "document.pdf"
    except Exception:
        return "document.pdf"


def _title_from_url(url: str, brand: str, model: str) -> str:
    stem = PurePosixPath(_filename_from_url(url)).stem.replace("_", " ").replace("-", " ")
    return stem if stem else f"{brand} {model}"


async def _search_pdf_urls(brand: str, model: str, template: str, max_results: int):
    query = template.format(brand=brand, model=model)
    doc_type = _doc_type_from_query(query)
    logger.info("Searching: %s", query)

    params = {
        "q": query,
        "api_key": SERPAPI_KEY,
        "num": max_results,
        "engine": "google",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get("https://serpapi.com/search", params=params)
            resp.raise_for_status()
            data = resp.json()

        urls = []
        for result in data.get("organic_results", []):
    link = result.get("link", "")
    if link:
        urls.append(link)

        logger.info("Found %d PDF URLs for '%s'", len(urls), query)
        return [(url, doc_type) for url in urls]

    except Exception as exc:
        logger.warning("SerpAPI error for '%s': %s", query, exc)
        return []


async def _download_pdf(url: str) -> Optional[bytes]:
    try:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True, headers=_HEADERS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content
            if len(data) > MAX_PDF_SIZE_BYTES:
                return None
            if not data.startswith(b"%PDF"):
                return None
            return data
    except Exception as exc:
        logger.warning("Download error for %s: %s", url[:80], exc)
        return None


async def collect_pdfs(request: CollectRequest) -> CollectResponse:
    errors = []
    pdfs_found = 0
    pdfs_uploaded = 0
    duplicates = 0

    for product in request.products:
        brand = product.brand.strip()
        model = product.model.strip()
        logger.info("Processing: %s %s", brand, model)

        candidate_pairs = []
        for template in QUERY_TEMPLATES:
            pairs = await _search_pdf_urls(brand, model, template, request.max_results_per_query)
            candidate_pairs.extend(pairs)
            await asyncio.sleep(0.5)

        seen_urls = set()
        unique_pairs = []
        for url, dtype in candidate_pairs:
            if url not in seen_urls:
                seen_urls.add(url)
                unique_pairs.append((url, dtype))

        for url, doc_type in unique_pairs:
            pdfs_found += 1
            pdf_bytes = await _download_pdf(url)
            if pdf_bytes is None:
                errors.append(f"Download failed: {url[:100]}")
                continue

            sha = sha256_of_bytes(pdf_bytes)
            try:
                if await sha256_exists(sha):
                    duplicates += 1
                    continue
            except Exception as exc:
                errors.append(f"DB error: {exc}")
                continue

            filename = _filename_from_url(url)
            title = _title_from_url(url, brand, model)

            try:
                storage_path, storage_url = await upload_pdf(pdf_bytes, brand, model, sha, filename)
            except Exception as exc:
                errors.append(f"Upload error: {exc}")
                continue

            try:
                await insert_document(
                    brand=brand, model=model, title=title,
                    doc_type=doc_type, source_url=url,
                    storage_path=storage_path, storage_url=storage_url,
                    source="serpapi", sha=sha, file_size=len(pdf_bytes),
                )
                pdfs_uploaded += 1
            except Exception as exc:
                errors.append(f"DB insert error: {exc}")

    return CollectResponse(
        status="ok",
        products_processed=len(request.products),
        pdfs_found=pdfs_found,
        pdfs_uploaded=pdfs_uploaded,
        duplicates=duplicates,
        errors=errors,
    )
