from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class ProductQuery(BaseModel):
    brand: str
    model: str


class CollectRequest(BaseModel):
    products: List[ProductQuery]
    max_results_per_query: int = 5


class CollectResponse(BaseModel):
    status: str
    products_processed: int
    pdfs_found: int
    pdfs_uploaded: int
    duplicates: int
    errors: List[str]


class DocumentRecord(BaseModel):
    id: Optional[str]
    created_at: Optional[str]
    brand: Optional[str]
    model: Optional[str]
    title: Optional[str]
    doc_type: Optional[str]
    source_url: Optional[str]
    storage_path: Optional[str]
    storage_url: Optional[str]
    source: Optional[str]
    sha256: Optional[str]
    file_size: Optional[int]

    class Config:
        orm_mode = True
