"""FastAPI app: POST list of HomeDepot PDP URLs (stream) + GET single URL / product id -> JSON {success, product_id, store_id, zip_code, html}."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from config import settings
from schemas import PDPRequest, PDPResponse, PDPResult
from scraper.homedepot_pdp import scrape_pdp
import re

state: dict = {}

# ───────────── API logs (alag Mongo server) ─────────────
# Render env me set karo (code me password mat likhna):
#   LOG_MONGO_URI = mongodb://<user>:<password>@<host>:27017/?authSource=admin
#   LOG_MONGO_DB  = Homedepot_API_logs
LOG_MONGO_URI = os.getenv("LOG_MONGO_URI", "")
LOG_MONGO_DB = os.getenv("LOG_MONGO_DB", "Homedepot_API_logs")
IST = timezone(timedelta(hours=5, minutes=30))   # roz ki collection IST date se: 2026_11_17

logger = logging.getLogger("homedepot_api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def today_collection():
    """Aaj ki collection: Homedepot_API_logs.2026_11_17"""
    db = state.get("log_db")
    if db is None:
        return None
    return db[datetime.now(IST).strftime("%Y_%m_%d")]


async def save_log(doc: dict):
    """Log Mongo me daalo. Mongo down ho to bhi API na ruke."""
    try:
        col = today_collection()
        if col is not None:
            await col.insert_one(doc)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"log save failed: {type(e).__name__}: {e}")


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

    state["log_db"] = None
    if LOG_MONGO_URI:
        from motor.motor_asyncio import AsyncIOMotorClient

        log_client = AsyncIOMotorClient(LOG_MONGO_URI, serverSelectionTimeoutMS=5000)
        state["log_db"] = log_client[LOG_MONGO_DB]
        try:
            await log_client.admin.command("ping")
            logger.info(f"log mongo connected: {LOG_MONGO_DB}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"log mongo not reachable: {type(e).__name__}: {e}")
    yield
    await state["client"].aclose()


app = FastAPI(title="HomeDepot PDP API", version="1.0", lifespan=lifespan)



@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Har API hit ka log: console (Render Logs) + Mongo (aaj ki collection)."""
    start = time.perf_counter()
    try:
        response = await call_next(request)
        status = response.status_code
        stock_status = response.headers.get("X-Stock-Status")
        error = response.headers.get("X-Error")
    except Exception as e:  # noqa: BLE001
        status, stock_status, error, response = 500, None, f"{type(e).__name__}: {e}", None
    ms = round((time.perf_counter() - start) * 1000)

    q = dict(request.query_params)
    doc = {
        "ts": datetime.now(timezone.utc),
        "ts_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
        "method": request.method,
        "path": request.url.path,
        "product_id": request.path_params.get("pro_id") or request.url.path.rstrip("/").split("/")[-1],
        "url_param": q.get("url"),
        "store_id": q.get("store_id"),
        "zip_code": q.get("zip_code"),
        "query": q,
        "status": status,
        "success": 200 <= status < 300,
        "duration_ms": ms,
        "ip": (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
              or (request.client.host if request.client else None),
        "user_agent": request.headers.get("user-agent"),
        "stock_status": stock_status,
        "error": error,
    }
    logger.info(f'{doc["method"]} {doc["path"]} store={doc["store_id"]} zip={doc["zip_code"]} '
                f'-> {status} {ms}ms | {error or stock_status or ""}')
    if request.url.path != "/health":
        asyncio.create_task(save_log(doc))   # background me, response slow nahi hoga

    if response is None:
        return HTMLResponse(content="internal error", status_code=500)
    return response


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


def safe_header(v) -> str:
    """Header value: single line, printable ASCII only, short."""
    return re.sub(r"[^\x20-\x7E]+", " ", str(v)).strip()[:150]


def pdp_json_response(res: dict, url: str, store_id: str | None, zip_code: str | None):
    """Final response format: {success, status, product_id, store_id, zip_code, html}."""
    m = PRODUCT_ID_RE.search(url)
    base = {
        "product_id": m.group(1) if m else None,
        "store_id": store_id,
        "zip_code": zip_code,
    }
    # headers = {"X-Stock-Status": str(res.get("stock_status", "n/a"))}
    headers = {"X-Stock-Status": safe_header(res.get("stock_status", "n/a"))}

    if not res["status"].startswith("success"):
        headers["X-Error"] = safe_header(res.get("error") or "failed")
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


def pdp_html_response(res: dict, url: str, store_id: str | None, zip_code: str | None):
    """Client ko sirf raw HTML chahiye -- no JSON wrapper, no success/status/product_id fields.
    Success: raw PDP HTML, status 200.
    Failure: short plain error text, status 502.
    (Stock status still goes in the X-Stock-Status header for debugging, not in the body.)"""
    headers = {"X-Stock-Status": safe_header(res.get("stock_status", "n/a"))}

    if not res["status"].startswith("success"):
        headers["X-Error"] = safe_header(res.get("error") or "failed")   # log me error dikhe
        return HTMLResponse(
            content=res.get("error") or "failed",
            status_code=502,
            headers=headers,
        )

    return HTMLResponse(
        content=res["data"],
        status_code=200,
        headers=headers,
    )


@app.get("/health")
async def health():
    credits_info = {}
    token = settings.scrapedo_token

    if token:
        try:
            resp = await state["client"].get(
                "https://api.scrape.do/info",
                params={"token": token},
            )
            data = resp.json()
            credits_info = {
                "scrape_do_active": data.get("IsActive"),
                "scrape_do_remaining_monthly_requests": data.get("RemainingMonthlyRequest"),
                "scrape_do_max_monthly_requests": data.get("MaxMonthlyRequest"),
                "scrape_do_remaining_concurrent": data.get("RemainingConcurrentRequest"),
            }
        except Exception as e:
            credits_info = {"scrape_do_error": str(e)}

    return {"status": "ok", **credits_info}


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
    # return pdp_json_response(res, url, store_id, zip_code)
    return pdp_html_response(res, url, store_id, zip_code)


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
    # return pdp_json_response(res, url, store_id, zip_code)
    return pdp_html_response(res, url, store_id, zip_code)