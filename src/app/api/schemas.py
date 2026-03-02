from typing import List, Optional
from pydantic import BaseModel


class ConvertItemResponse(BaseModel):
    filename: str
    fmt: str
    provider: str
    md_content: Optional[str] = None
    error: Optional[str] = None


class ConvertResponse(BaseModel):
    job_id: str
    results: List[ConvertItemResponse]