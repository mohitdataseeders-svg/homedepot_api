from typing import Any
from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlparse


class PDPRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, description="HomeDepot PDP URLs")
    store_id: str | None = Field(None, description="HomeDepot store id (store based pricing)")
    zip_code: str | None = None
    use_cache: bool = True

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, urls: list[str]) -> list[str]:
        clean, seen = [], set()
        for u in urls:
            u = u.strip()
            host = urlparse(u).netloc.lower()
            if not (host == "homedepot.com" or host.endswith(".homedepot.com")):
                raise ValueError(f"Not a homedepot.com URL: {u}")
            if u not in seen:
                seen.add(u)
                clean.append(u)
        return clean


class PDPResult(BaseModel):
    url: str
    status: str  # success | failed
    cached: bool = False
    data: dict[str, Any] | None = None
    error: str | None = None


class PDPResponse(BaseModel):
    requested: int
    success: int
    failed: int
    results: list[PDPResult]
