"""HomeDepot PDP scraper (script 2).

Fetches the page through scrape.do and parses embedded JSON (JSON-LD first,
regex fallbacks second). Never raises: always returns a dict with a status.

Can be tested standalone:
    python -m scraper.homedepot_pdp <pdp_url> [store_id]
"""
import asyncio
import json
import re
import sys
from urllib.parse import quote

import httpx

from config import settings

SCRAPEDO = "https://api.scrape.do/"


def build_scrapedo_url(url: str, store_id: str | None, zip_code: str | None) -> str:
    # params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us&super=true"
    params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us"
    # Store based pricing: HomeDepot reads the store from the THD_LOCALIZER /
    # THD_PERSIST cookies. VERIFY the exact cookie format on a real request
    # and adjust here if needed.
    cookies = []
    if store_id:
        cookies.append(f"THD_PERSIST=C4%3D{store_id}%2B%2B%3BC4_EXP%3D9999999999")
    if zip_code:
        cookies.append(f"THD_LOCALIZER=%7B%22WORKFLOW%22%3A%22LOCALIZED_BY_ZIP%22%7D")
    if cookies:
        params += "&setCookies=" + quote(";".join(cookies), safe="")
    return f"{SCRAPEDO}?{params}"


JSONLD_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I
)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")


def _jsonld_product(html: str) -> dict:
    for block in JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict):
                if item.get("@type") == "Product":
                    return item
                for g in item.get("@graph", []) or []:
                    if isinstance(g, dict) and g.get("@type") == "Product":
                        return g
    return {}


def parse_pdp(html: str, url: str) -> dict:
    p = _jsonld_product(html)

    offers = p.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    rating = p.get("aggregateRating") or {}
    brand = p.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    images = p.get("image") or []
    if isinstance(images, str):
        images = [images]

    m = re.search(r"/(\d{6,})(?:[/?#]|$)", url)
    item_id = m.group(1) if m else None

    title = p.get("name")
    if not title:
        m_h1 = H1_RE.search(html)
        title = TAG_RE.sub("", m_h1.group(1)).strip() if m_h1 else None

    data = {
        "item_id": item_id,
        "sku": p.get("sku"),
        "model": p.get("model"),
        "title": title,
        "brand": brand,
        "description": p.get("description"),
        "price": offers.get("price"),
        "currency": offers.get("priceCurrency"),
        "availability": offers.get("availability"),
        "rating": rating.get("ratingValue"),
        "review_count": rating.get("reviewCount"),
        "images": images,
        "url": url,
    }
    if not data["title"] and not data["price"]:
        raise ValueError("Parsing failed: page has no product data (blocked or layout changed)")
    return data


async def scrape_pdp(
    url: str,
    store_id: str | None = None,
    zip_code: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    last_err = "unknown error"
    try:
        for attempt in range(1, settings.retries + 1):
            try:
                r = await client.get(build_scrapedo_url(url, store_id, zip_code))
                if r.status_code == 200:
                    # parsing alag thread me, taaki event loop block na ho
                    data = await asyncio.to_thread(parse_pdp, r.text, url)
                    return {"url": url, "status": "success", "data": data}
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code in (400, 401, 404):
                    break  # retry se koi fayda nahi
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}: {e}"
            await asyncio.sleep(0.5 * attempt)
        return {"url": url, "status": "failed", "error": last_err}
    finally:
        if own_client:
            await client.aclose()


if __name__ == "__main__":
    out = asyncio.run(scrape_pdp(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
    print(json.dumps(out, indent=2))
