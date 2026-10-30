"""HomeDepot PDP scraper (simple version).

Sirf 2 requests (dono parallel):
  1) PDP HTML (scrape.do)
  2) StoreSearchServices -> store ka poora data

StoreSearch ka data HTML me:
  - __EXPERIENCE_CONTEXT__ me storeId / storeName / storeZip / localStoreZip / deliveryZip replace
  - __APOLLO_OPERATIONS me storeId replace
  - </body> se pehle <script id="store-search-data"> me poora raw response

Never raises: hamesha {"status": ...} dict return karta hai.

Test:
    python -m scraper.homedepot_pdp <pdp_url> [store_id] [zip_code]
"""
import asyncio
import json
import re
import sys
from urllib.parse import quote

import httpx

from config import settings

SCRAPEDO = "https://api.scrape.do/"
STORESEARCH_URL = "https://www.homedepot.com/StoreSearchServices/v2/storesearch"


# ───────────────────────── scrape.do URLs ─────────────────────────
def build_scrapedo_get_url(target_url: str) -> str:
    return f"{SCRAPEDO}?token={settings.scrapedo_token}&url={quote(target_url, safe='')}&geoCode=us"


def build_scrapedo_url(url: str, store_id: str | None, zip_code: str | None) -> str:
    params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us"
    cookies = []
    if store_id:
        cookies.append(f"THD_PERSIST=C4%3D{store_id}%2B%2B%3BC4_EXP%3D9999999999")
    if zip_code:
        cookies.append(f"DELIVERY_ZIP={zip_code}")
        cookies.append("DELIVERY_ZIP_TYPE=USER")
    if cookies:
        params += "&setCookies=" + quote(";".join(cookies), safe="")
    return f"{SCRAPEDO}?{params}"


# ───────────────────────── requests ─────────────────────────
async def lookup_store(store_id: str, client: httpx.AsyncClient) -> dict | None:
    """StoreSearchServices se poora store object (raw)."""
    url = f"{STORESEARCH_URL}?storeid={store_id}&type=json"
    for attempt in range(1, settings.retries + 1):
        try:
            r = await client.get(build_scrapedo_get_url(url))
            if r.status_code == 200:
                stores = (r.json() or {}).get("stores") or []
                return stores[0] if stores else None
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(0.5 * attempt)
    return None


async def fetch_pdp_html(url: str, store_id: str | None, zip_code: str | None,
                         client: httpx.AsyncClient) -> dict:
    last_err = "unknown error"
    for attempt in range(1, settings.retries + 1):
        try:
            r = await client.get(build_scrapedo_url(url, store_id, zip_code))
            if r.status_code == 200:
                return {"status": "success", "html": r.text}
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 404):
                break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        await asyncio.sleep(0.5 * attempt)
    return {"status": "failed", "error": last_err}


# ───────────────────────── HTML me store data ─────────────────────────
def _dump_js_safe(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _store_fields(store: dict, store_id: str) -> tuple[str, str, str]:
    """StoreSearch response se id / name / zip (field names thode alag ho sakte hain)."""
    addr = store.get("address") or {}
    sid = str(store.get("storeId") or store_id)
    name = store.get("name") or store.get("storeName") or ""
    szip = str(addr.get("postalCode") or addr.get("zip") or store.get("zipCode") or "")[:5]
    return sid, name, szip


def apply_store_to_html(html: str, store: dict, store_id: str, zip_code: str | None) -> str:
    sid, name, szip = _store_fields(store, store_id)

    def sub(seg: str, key: str, val: str) -> str:
        return re.sub(rf'("{key}"\s*:\s*")[^"]*(")',
                      lambda m: m.group(1) + val + m.group(2), seg)

    # 1) __EXPERIENCE_CONTEXT__
    i = html.find("window.__EXPERIENCE_CONTEXT__")
    if i != -1:
        j = html.find("</script>", i)
        seg = html[i:j]
        seg = sub(seg, "storeId", sid)
        seg = sub(seg, "storeName", name)
        seg = sub(seg, "storeZip", szip)
        seg = sub(seg, "localStoreZip", szip)
        if zip_code:
            seg = sub(seg, "deliveryZip", zip_code)
        html = html[:i] + seg + html[j:]

    # 2) __APOLLO_OPERATIONS -> storeId
    m = re.search(r"__APOLLO_OPERATIONS\s*=\s*", html)
    if m:
        try:
            start = html.find("{", m.end() - 1)
            ops, n = json.JSONDecoder().raw_decode(html[start:])
            for op in ops.get("operations", []):
                v = op.get("variables")
                if isinstance(v, dict) and "storeId" in v:
                    v["storeId"] = sid
            html = html[:start] + _dump_js_safe(ops) + html[start + n:]
        except Exception:  # noqa: BLE001
            pass

    # 3) poora StoreSearch response ek script tag me
    block = f'<script id="store-search-data" type="application/json">{_dump_js_safe(store)}</script>'
    k = html.lower().rfind("</body>")
    return (html[:k] + block + html[k:]) if k != -1 else (html + block)


# ───────────────────────── main entry ─────────────────────────
async def scrape_pdp(url: str, store_id: str | None = None, zip_code: str | None = None,
                     client: httpx.AsyncClient | None = None) -> dict:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        if store_id:
            store_id = str(int(store_id))  # "0115" -> "115"

        if not store_id:
            pdp = await fetch_pdp_html(url, None, zip_code, client)
            if pdp["status"] != "success":
                return {"url": url, "status": "failed", "error": pdp["error"]}
            return {"url": url, "status": "success 200", "data": pdp["html"], "stock_status": "n/a"}

        # dono requests parallel
        store, pdp = await asyncio.gather(
            lookup_store(store_id, client),
            fetch_pdp_html(url, store_id, zip_code, client),
        )

        if store is None:
            return {"url": url, "status": "failed",
                    "error": f"store_id {store_id} not found via StoreSearchServices"}
        if pdp["status"] != "success":
            return {"url": url, "status": "failed", "error": pdp["error"]}

        html = apply_store_to_html(pdp["html"], store, store_id, zip_code)
        return {"url": url, "status": "success 200", "data": html, "stock_status": "store-search"}
    finally:
        if own_client:
            await client.aclose()


if __name__ == "__main__":
    out = asyncio.run(scrape_pdp(
        sys.argv[1],
        sys.argv[2] if len(sys.argv) > 2 else None,
        sys.argv[3] if len(sys.argv) > 3 else None,
    ))
    html = out.get("data", "")
    ctx = re.search(r'"storeId":"(\d+)","storeName":"([^"]*)","storeZip":"(\d*)"', html)
    print(out["status"], out.get("stock_status"), ctx.groups() if ctx else out.get("error"))