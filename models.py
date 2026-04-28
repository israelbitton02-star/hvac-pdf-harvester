from typing import Optional, List
from pydantic import BaseModel

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
    brand: Optional[str]
    modele: Optional[str]
    title: Optional[str]
    sha256: Optional[str]
