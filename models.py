from typing import Optional, List
from pydantic import BaseModel


class ProductQuery(BaseModel):
    brand: str
    model_name: str

    class Config:
        fields = {'model_name': 'model'}


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
    id: Optional[str] = None
    created_at: Optional[str] = None
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
        orm_mode = True
