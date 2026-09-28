"""FastAPI app (script 1): POST a list of HomeDepot PDP URLs, get data back."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from fastapi.security import APIKeyHeader

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from config import settings
from schemas import PDPRequest, PDPResponse, PDPResult
from scraper.homedepot_pdp import scrape_pdp

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["client"] = httpx.AsyncClient(
        timeout=settings.request_timeout,
        limits=httpx.Limits(max_connections=settings.concurrency * 2),
    )
    state["sem"] = asyncio.Semaphore(settings.concurrency)
    state["cache"] = None
    if settings.mongo_uri:
        from motor.motor_asyncio import AsyncIOMotorClient

        mongo = AsyncIOMotorClient(settings.mongo_uri)
        state["cache"] = mongo[settings.mongo_db]["pdp_cache"]
        await state["cache"].create_index("url")
    yield
    await state["client"].aclose()


app = FastAPI(title="HomeDepot PDP API", version="1.0", lifespan=lifespan)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def check_key(x_api_key: str | None = Depends(api_key_header)):
    keys = settings.api_key_list
    if keys and x_api_key not in keys:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def cache_key(url: str, store_id: str | None) -> dict:
    return {"url": url, "store_id": store_id}


async def get_cached(url: str, store_id: str | None):
    col = state["cache"]
    if col is None:
        return None
    doc = await col.find_one(cache_key(url, store_id))
    if doc and doc["scraped_at"] > datetime.now(timezone.utc) - timedelta(hours=settings.cache_ttl_hours):
        return doc["data"]
    return None


async def save_cache(url: str, store_id: str | None, data: dict):
    col = state["cache"]
    if col is not None:
        await col.update_one(
            cache_key(url, store_id),
            {"$set": {"data": data, "scraped_at": datetime.now(timezone.utc)}},
            upsert=True,
        )


async def process(url: str, req: PDPRequest) -> PDPResult:
    if req.use_cache:
        cached = await get_cached(url, req.store_id)
        if cached:
            return PDPResult(url=url, status="success", cached=True, data=cached)
    async with state["sem"]:
        res = await scrape_pdp(url, req.store_id, req.zip_code, state["client"])
    if res["status"] == "success":
        await save_cache(url, req.store_id, res["data"])
    return PDPResult(**res)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/homedepot/pdp/stream", dependencies=[Depends(check_key)])
async def homedepot_pdp_stream(req: PDPRequest):
    if len(req.urls) > settings.max_urls_per_request:
        raise HTTPException(400, f"Max {settings.max_urls_per_request} URLs per request")

    async def gen():
        tasks = [asyncio.create_task(process(u, req)) for u in req.urls]
        for fut in asyncio.as_completed(tasks):
            r = await fut
            yield r.model_dump_json() + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")
