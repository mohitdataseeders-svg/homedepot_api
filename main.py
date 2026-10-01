"""FastAPI app: POST list of HomeDepot PDP URLs (stream) + GET single URL / product id -> JSON {success, product_id, store_id, zip_code, html}."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader

from config import settings
from schemas import PDPRequest, PDPResponse, PDPResult
from scraper.homedepot_pdp import scrape_pdp
import re

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

async def fetch_html(url: str, store_id: str | None, zip_code: str | None):
    """Raw HTML directly from scrape_pdp (no PDPResult schema, no cache)."""
    async with state["sem"]:
        res = await scrape_pdp(url, store_id, zip_code, state["client"])
    return res


PRODUCT_ID_RE = re.compile(r"/(\d{6,})(?:[/?#]|$)")


def pdp_json_response(res: dict, url: str, store_id: str | None, zip_code: str | None):
    """Final response format: {success, status, product_id, store_id, zip_code, html}."""
    m = PRODUCT_ID_RE.search(url)
    base = {
        "product_id": m.group(1) if m else None,
        "store_id": store_id,
        "zip_code": zip_code,
    }
    headers = {"X-Stock-Status": str(res.get("stock_status", "n/a"))}

    if not res["status"].startswith("success"):
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "status": 502,
                **base,
                "error": res.get("error") or "failed",
            },
            headers=headers,
        )

    return JSONResponse(
        status_code=200,
        content={"success": True, "status": 200, **base, "html": res["data"]},
        headers=headers,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- POST (batch, streaming NDJSON) ----------
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


# ---------- GET by URL (browser-friendly JSON, public) ----------
@app.get("/v1/homedepot/pdp")
async def homedepot_pdp_get(
    url: str = Query(..., description="HomeDepot product URL"),
    store_id: str | None = Query(None, description="Optional store id"),
    zip_code: str | None = Query(None, description="Optional zip code"),
    use_cache: bool = Query(True, description="Use Mongo cache if available"),
):
    # ---- OLD JSON VERSION ----
    # url = unquote(url)
    # req = PDPRequest(urls=[url],store_id=store_id,zip_code=zip_code,use_cache=use_cache)
    # result = await process(url, req)
    # if result.status != "success":
    #     return JSONResponse(status_code=502, content=result.model_dump())
    # return result.model_dump()

    # ---- NEW JSON(html) VERSION ----
    url = unquote(url)
    res = await fetch_html(url, store_id, zip_code)
    return pdp_json_response(res, url, store_id, zip_code)


# ---------- GET by PRODUCT ID (browser-friendly JSON, public) ----------
@app.get("/v1/homedepot/pdp/{pro_id}")
async def homedepot_pdp_get_by_id(
    pro_id: str,
    store_id: str | None = Query(None, description="Optional store id"),
    zip_code: str | None = Query(None, description="Optional zip code"),
    use_cache: bool = Query(True, description="Use Mongo cache if available"),
):
    if not pro_id.isdigit():
        raise HTTPException(400, "pro_id must be numeric (e.g. 206616823)")

    url = f"https://www.homedepot.com/p/{pro_id}"

    # ---- OLD JSON VERSION ----
    # req = PDPRequest(urls=[url],store_id=store_id,zip_code=zip_code,use_cache=use_cache,)
    # result = await process(url, req)
    # if result.status != "success":
    #     return JSONResponse(status_code=502, content=result.model_dump())
    # return result.model_dump()

    # ---- NEW JSON(html) VERSION ----
    res = await fetch_html(url, store_id, zip_code)
    return pdp_json_response(res, url, store_id, zip_code)