"""HomeDepot PDP scraper (scrape.do HomeDepot plugin).

Har request pe sirf 1 call:
    https://api.scrape.do/plugin/homedepot/product?token=...&storeid=<id>&zipcode=<zip>&url=<pdp_url>

scrape.do ka plugin khud store / zip set karke PDP HTML deta hai, jisme
store-wise price, stock aur store details already hote hain.
Alag GraphQL / StoreSearch request ki zaroorat nahi.

Test:
    python -m scraper.homedepot_pdp https://www.homedepot.com/p/335644555 154 30328
"""
import asyncio
import re
import sys
from urllib.parse import quote

import httpx

from config import settings

SCRAPEDO_PLUGIN = "https://api.scrape.do/plugin/homedepot/product"
STORE_CTX_RE = re.compile(r'"storeId"\s*:\s*"(\d+)"\s*,\s*"storeName"\s*:\s*"([^"]*)"\s*,\s*"storeZip"\s*:\s*"(\d*)"')


def build_plugin_url(url: str, store_id: str | None, zip_code: str | None) -> str:
    params = f"token={settings.scrapedo_token}"
    if store_id:
        params += f"&storeid={store_id}"
    if zip_code:
        params += f"&zipcode={zip_code}"
    params += f"&url={quote(url, safe='')}"
    return f"{SCRAPEDO_PLUGIN}?{params}"


def _store_check(html: str, store_id: str | None) -> str:
    """Debug ke liye: HTML me kaunsa store aaya (X-Stock-Status header me dikhega)."""
    m = STORE_CTX_RE.search(html)
    if not m:
        return "plugin (store context not found)"
    sid, name, szip = m.groups()
    if store_id and int(sid) != int(store_id):
        return f"plugin (store mismatch: {sid} {name})"
    return f"plugin (store {sid} {name} {szip})"


async def scrape_pdp(url: str, store_id: str | None = None, zip_code: str | None = None,
                     client: httpx.AsyncClient | None = None) -> dict:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        if store_id:
            store_id = str(int(store_id))  # "0115" -> "115"

        last_err = "unknown error"
        for attempt in range(1, settings.retries + 1):
            try:
                r = await client.get(build_plugin_url(url, store_id, zip_code))
                if r.status_code == 200:
                    html = r.text
                    return {"url": url, "status": "success 200", "data": html,
                            "stock_status": _store_check(html, store_id)}
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
    out = asyncio.run(scrape_pdp(
        sys.argv[1],
        sys.argv[2] if len(sys.argv) > 2 else None,
        sys.argv[3] if len(sys.argv) > 3 else None,
    ))
    print(out["status"], out.get("stock_status") or out.get("error"))