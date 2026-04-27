from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ProductQuery(BaseModel):
    brand: str = Field(..., example="Atlantic")
    model: str = Field(..., example="Calypso")


class CollectRequest(BaseModel):
    products: list[ProductQuery] = Field(..., min_length=1)
    max_results_per_query: int = Field(default=5, ge=1, le=20)


class CollectResponse(BaseModel):
    status: str
    products_processed: int
    pdfs_found: int
    pdfs_uploaded: int
    duplicates: int
    errors: list[str]


class DocumentRecord(BaseModel):
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    title: Optional[str] = None
    doc_type: Optional[str] = None
    source_url: Optional[str] = None
    storage_path: Optional[str] = None
    storage_url: Optional[str] = None
    source: Optional[str] = None
    sha256: Optional[str] = None
    file_size: Optional[int] = None

    class Config:
        from_attributes = True
