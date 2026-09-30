"""HomeDepot PDP scraper (script 2) - full field extraction.

Fetches the page through scrape.do and parses:
  - JSON-LD Product / Breadcrumb blocks
  - Apollo state (window.__APOLLO_STATE__) for extended attributes
  - Store/experience context

Never raises: always returns a dict with a status.
Only uses data returned by the single scrape.do request -- no extra
requests are made for variations. For variations, only IDs are kept
(not full per-variant image/price/url payloads).

Can be tested standalone:
    python -m scraper.homedepot_pdp <pdp_url> [store_id]
"""
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from parsel import Selector

from config import settings

SCRAPEDO = "https://api.scrape.do/"


def c_replace(html=""):
    """Clean HTML content (recursive: str / list / dict, other types pass through)"""
    if isinstance(html, str):
        html = html.replace("&gt;", ">")
        html = html.replace("&lt;", "<")
        html = html.replace("&amp;", "&")
        html = html.replace("&nbsp;", " ")
        html = html.replace("\r\n", " ")
        html = html.replace("\t", " ")
        html = html.replace("\n", " ")
        html = html.replace("\r", " ")
        html = html.replace("<p>", " ")
        html = html.replace("</p>", " ")
        html = html.replace("<ul>", " ")
        html = html.replace("</ul>", " ")
        html = html.replace("/<ul>", " ")
        html = html.replace("<li>", " ")
        html = html.replace("</li>", " ")
        html = html.replace("™", "")
        html = html.replace("\u200b", "")

        html = re.sub(
            r"\* style specs start[^>]*>([\w\W]*?)style specs end \*", " ", html
        )
        html = re.sub(r"<script[^>]*>([\w\W]*?)</script>", " ", html)
        html = re.sub(r"<style[^>]*>([\w\W]*?)</style>", " ", html)
        html = re.sub(r"<!--([\w\W]*?)-->", " ", html)
        html = re.sub(r"<([\w\W]*?)>", " ", html)
        html = re.sub(r"<.*?>", " ", html)
        html = re.sub(r" +", " ", html)
        return html.strip()

    elif isinstance(html, list):
        # keep non-empty items; don't drop 0 / False / None-safe values wrongly
        cleaned = [c_replace(i) for i in html]
        return [j for j in cleaned if j not in ("", None, [], {})]

    elif isinstance(html, dict):
        return {k: c_replace(v) for k, v in html.items()}

    else:
        # int, float, bool, None -> leave untouched
        return html


def build_scrapedo_url(url: str, store_id: str | None, zip_code: str | None) -> str:
    params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us"
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
STORE_CTX_RE = re.compile(
    r'"storeId":\s*"(\d+)",\s*"storeName":\s*"([^"]*)",\s*"storeZip":\s*"(\d+)"'
)


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


def _breadcrumb(sel: Selector) -> tuple[str, str]:
    bread_js = sel.xpath(
        '//script[@id="thd-helmet__script--breadcrumbStructureData"]//text()'
    ).get()
    if not bread_js:
        return "", ""
    try:
        nos = json.loads(bread_js)
    except json.JSONDecodeError:
        return "", ""
    items = (nos.get("breadcrumb") or {}).get("itemListElement", [])
    names = [i.get("item", {}).get("name", "") for i in items if i.get("item", {}).get("name")]
    return " > ".join(names), (names[-1] if names else "")


def _apollo_state(sel: Selector) -> dict:
    apollo_txt = sel.xpath(
        '//script[contains(text(),"window.__APOLLO_STATE__")]/text()'
    ).get() or ""
    if not apollo_txt:
        return {}
    try:
        start = apollo_txt.find("{", apollo_txt.find("__APOLLO_STATE__"))
        apollo, _ = json.JSONDecoder().raw_decode(apollo_txt[start:])
        return apollo
    except Exception:
        return {}


def _variation_ids(apollo: dict, prod_node: dict) -> list[str]:
    """IDs of other color/size variants only, from data already fetched in
    this same request -- no extra HTTP calls, no full per-variant payload."""
    ids = set()

    # common shapes on the product node itself
    for key in ("variantSkus", "variations", "siblingProducts", "colorVariants"):
        node = prod_node.get(key)
        if isinstance(node, list):
            for v in node:
                if isinstance(v, dict):
                    vid = v.get("productId") or v.get("itemId") or v.get("id") or v.get("sku")
                    if vid:
                        ids.add(str(vid))
                elif isinstance(v, str):
                    ids.add(v)

    # fallback: every other product node present in this same apollo payload
    for key in apollo:
        if key.startswith("base-catalog-"):
            ids.add(key.replace("base-catalog-", ""))

    return sorted(ids)


def parse_pdp(html: str, url: str) -> dict:
    p = _jsonld_product(html)
    sel = Selector(text=html)

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

    seen = set()
    unique_urls = []

    for img in images:
        img = re.sub(r'_\d+\.jpg$', '_1000.jpg', img)
        if img not in seen:
            seen.add(img)
            unique_urls.append(img)

    result = "\n".join(unique_urls)

    m = re.search(r"/(\d{6,})(?:[/?#]|$)", url)
    item_id = m.group(1) if m else None
    product_id = p.get("productID", "") or item_id or ""

    # title = p.get("name")
    # if not title:
    #     m_h1 = H1_RE.search(html)
    #     title = TAG_RE.sub("", m_h1.group(1)).strip() if m_h1 else None

    product_name = p.get("name", "")

    if brand and product_name.lower().startswith(brand.lower()):
        product_name = product_name[len(brand):].lstrip(" -:,|").strip()

    breadcrumb, category = _breadcrumb(sel)

    # ── Apollo state (rich product JSON) ────────────────────────────
    apollo = _apollo_state(sel)
    prod_node = apollo.get(f"base-catalog-{product_id}", {})
    if not prod_node:
        prod_node = next((v for k, v in apollo.items() if k.startswith("base-catalog-")), {})

    identifiers = prod_node.get("identifiers") or {}
    info_node = prod_node.get("info") or {}
    avail_node = prod_node.get("availabilityType") or {}
    details_node = prod_node.get("details") or {}
    media_node = prod_node.get("media") or {}

    pricing_key = next((k for k in prod_node if k.startswith("pricing(")), None)
    pricing_node = prod_node.get(pricing_key) or {} if pricing_key else {}
    promo_node = pricing_node.get("promotion") or {}
    bundle_promo = (pricing_node.get("bundlePromotionalAdjustments") or [{}])[0] or {}
    bundle_promo_dates = bundle_promo.get("dates") or {}

    seo_desc = prod_node.get("seo", {}).get("seoDescription", "")

    apollo_videos = media_node.get("video", []) or []
    videos = " | ".join(v.get("url", "") for v in apollo_videos if v.get("url"))

    key_features = {}
    for kf_item in ((prod_node.get("keyProductFeatures") or {}).get("keyProductFeaturesItems") or []):
        for feat in (kf_item.get("features") or []):
            key_features[feat.get("name")] = feat.get("value")

    specifications = {}
    for grp in (prod_node.get("specificationGroup") or []):
        grp_dict = {}
        for sp in (grp.get("specifications") or []):
            grp_dict[sp.get("specName")] = sp.get("specValue")
        specifications[grp.get("specTitle")] = grp_dict

    root_q = apollo.get("ROOT_QUERY", {})
    qa_key = next((k for k in root_q if k.startswith("questionsAnswers(")), None)
    qa_node = root_q.get(qa_key) or {} if qa_key else {}
    qa_results = [
        {
            "question": q.get("QuestionSummary"),
            "user": q.get("UserNickname"),
            "date": q.get("SubmissionTime"),
            "answers": q.get("TotalAnswerCount"),
        }
        for q in (qa_node.get("Results") or [])
    ]

    canonical_link = sel.xpath('//link[@rel="canonical"]/@href').get() or ""
    savings_text = (sel.xpath('//p[@data-testid="product-savings"]/text()').get() or "") + (
        sel.xpath('//p[@data-testid="product-savings"]/text()[2]').get() or ""
    )
    subtotal_text = sel.xpath('//p[@data-testid="subtotal"]/text()').get() or ""
    retail_text = sel.xpath('//p[@data-testid="retail-price"]/text()').get() or ""

    stock = "InStock" if avail_node.get("buyable") == "true" else "OutOfStock"

    ctx_txt = sel.xpath('//script[contains(text(),"__EXPERIENCE_CONTEXT__")]/text()').get() or ""
    m_sid = STORE_CTX_RE.search(ctx_txt)
    store_id_ctx, store_name, store_zip = (m_sid.groups() if m_sid else ("", "", ""))

    variation_ids = _variation_ids(apollo, prod_node)

    hashid_prod = hashlib.md5(url.encode("utf-8")).hexdigest()
    iso_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    price_str = offers.get("price", "")
    mrp = offers.get("priceSpecification", {}).get("price", "")

    if price_str:
        price = float(price_str)
    else:
        price = float(mrp) if mrp else 0.0

    if not mrp:
        mrp = price

    data = {
        "_id": hashid_prod,
        "item_id": item_id,
        "Product URL": canonical_link or url,
        "Product Name": product_name,
        "Product ID": product_id,
        "Brand": brand,
        "SKU": p.get("sku"),
        "Model": p.get("model"),
        "Datetime": iso_date,
        "Image URL": result,
        "Description": p.get("description"),
        "Category": category,
        "Breadcrumb": breadcrumb,
        "Sale Price": price,
        "Full Price": mrp,
        "Currency": offers.get("priceCurrency") or offers.get("currencyIso", "$"),
        "Rating": rating.get("ratingValue"),
        "ReviewCount": rating.get("reviewCount"),
        "Availability": offers.get("availability"),
        "Stock": stock,
        "Product Type": identifiers.get("productType", ""),
        "Model Number": identifiers.get("modelNumber", ""),
        "UPC": identifiers.get("upc", "") or identifiers.get("upcGtin13", ""),
        "Availability Type": avail_node.get("type", ""),
        "Is Discontinued": avail_node.get("discontinued", ""),
        "Is Obsolete": avail_node.get("obsolete", ""),
        "Hide Price": info_node.get("hidePrice", ""),
        "Quantity Limit": info_node.get("quantityLimit", ""),
        "Returnable": info_node.get("returnable", ""),
        "Promo Type": promo_node.get("type", ""),
        "Promo Dollar Off": promo_node.get("dollarOff", "") or bundle_promo.get("dollarOff", ""),
        "Promo Percent Off": promo_node.get("percentageOff", "") or bundle_promo.get("percentageOff", ""),
        "Promo ID": bundle_promo.get("promoId", ""),
        "Promo Start": bundle_promo_dates.get("start", ""),
        "Promo End": bundle_promo_dates.get("end", ""),
        "Savings Center": promo_node.get("savingsCenter", ""),
        "Displayed Retail Price": retail_text,
        "Displayed Savings": savings_text,
        "Displayed Subtotal": subtotal_text,
        "Price Valid Until": offers.get("priceValidUntil", ""),
        "Return Policy": (offers.get("hasMerchantReturnPolicy") or {}).get("returnPolicyCategory", ""),
        "Highlights": details_node.get("highlights") or [],
        "Key Features": key_features,
        "Specifications": specifications,
        "seoDescription": seo_desc,
        "QA List": qa_results,
        "Videos": videos,
        "Store ID": store_id_ctx,
        "Store Name": store_name,
        "Store Zip": store_zip,
        # only IDs -- no extra request made, no full per-variant payload kept
        "Variation IDs": variation_ids,
        "url": url,
    }

    if not data["Product Name"] and not data["Sale Price"]:
        raise ValueError("Parsing failed: page has no product data (blocked or layout changed)")
    return data
    # return html

# TODO : For Json

# async def scrape_pdp(
#     url: str,
#     store_id: str | None = None,
#     zip_code: str | None = None,
#     client: httpx.AsyncClient | None = None,
# ) -> dict:
#     own_client = client is None
#     client = client or httpx.AsyncClient(timeout=settings.request_timeout)
#     last_err = "unknown error"
#     try:
#         for attempt in range(1, settings.retries + 1):
#             try:
#                 r = await client.get(build_scrapedo_url(url, store_id, zip_code))
#                 if r.status_code == 200:
#                     # parsing alag thread me, taaki event loop block na ho
#                     data = await asyncio.to_thread(parse_pdp, r.text, url)
#                     return {"url": url, "status": "success 200", "data": data}
#                 last_err = f"HTTP {r.status_code}: {r.text[:200]}"
#                 if r.status_code in (400, 401, 404):
#                     break  # retry se koi fayda nahi
#             except Exception as e:  # noqa: BLE001
#                 last_err = f"{type(e).__name__}: {e}"
#             await asyncio.sleep(0.5 * attempt)
#         return {"url": url, "status": "failed", "error": last_err}
#     finally:
#         if own_client:
#             await client.aclose()

# TODO : For HTML

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
                    # raw HTML as-is, no parsing
                    return {"url": url, "status": "success 200", "html": r.text}
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