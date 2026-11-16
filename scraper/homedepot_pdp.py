"""HomeDepot PDP API -> HTML (master JSON + store-wise price/stock).

Har request pe 2 calls, dono parallel (scrape.do se):
  1) PDP HTML       -> normal scrape.do request (page + product details)
  2) Store data     -> scrape.do HomeDepot plugin  /plugin/homedepot/pdp
                       (store ka price, clearance, badges, on-hand stock, pickup, delivery)
  (+ StoreSearchServices: store ka naam / zip / hours. Har store ke liye sirf pehli baar,
     uske baad memory cache se.)

Plugin ka data HTML me:
  - __APOLLO_STATE__        : pricing / badges / fulfillment / availabilityType -> requested store ke
  - __APOLLO_OPERATIONS     : storeId -> requested store
  - __EXPERIENCE_CONTEXT__  : store object (id, name, zip, hours) + localStoreZip / deliveryZip
  - <script id="store-product-data">  : plugin ka poora JSON
  - <script id="product-data">        : master JSON (store price / stock ke saath)

Test:
    python -m scraper.homedepot_pdp https://www.homedepot.com/p/322138372 6175 10010
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
PLUGIN_PDP = "https://api.scrape.do/plugin/homedepot/pdp"
STORESEARCH_URL = "https://www.homedepot.com/StoreSearchServices/v2/storesearch"
ITEM_ID_RE = re.compile(r"/(\d{6,})(?:[/?#]|$)")

# scrape.do plan ki concurrency limit (429 se bachne ke liye). Env: SCRAPEDO_CONCURRENCY
SCRAPEDO_CONCURRENCY = int(getattr(settings, "scrapedo_concurrency", 0) or 5)
_sd_sem: asyncio.Semaphore | None = None

# Store ka naam / zip / hours roz nahi badalta -> memory cache
STORE_CACHE: dict[str, dict] = {}


async def sd_get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """scrape.do GET: concurrency limit ke andar; 429 aaye to ruk ke dobara."""
    global _sd_sem
    if _sd_sem is None:
        _sd_sem = asyncio.Semaphore(SCRAPEDO_CONCURRENCY)
    r = None
    for wait in (2, 4, 8, 16, None):
        async with _sd_sem:
            r = await client.get(url)
        if r.status_code != 429 or wait is None:
            return r
        await asyncio.sleep(wait)
    return r


# ───────────────────────── request 1: PDP HTML ─────────────────────────
def build_scrapedo_url(url: str, store_id: str | None, zip_code: str | None,
                       super_proxy: bool = False) -> str:
    params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us"
    if super_proxy:
        params += "&super=true"   # residential proxy: ROTATION_FAILED pe scrape.do yahi suggest karta hai
    cookies = []
    if store_id:
        cookies.append(f"THD_PERSIST=C4%3D{store_id}%2B%2B%3BC4_EXP%3D9999999999")
    if zip_code:
        cookies.append(f"DELIVERY_ZIP={zip_code}")
        cookies.append("DELIVERY_ZIP_TYPE=USER")
    if cookies:
        params += "&setCookies=" + quote(";".join(cookies), safe="")
    return f"{SCRAPEDO}?{params}"


async def fetch_pdp_html(url, store_id, zip_code, client) -> dict:
    last_err = "unknown error"
    for attempt in range(1, settings.retries + 1):
        try:
            # pehli try normal (sasti), baaki super proxy se
            r = await sd_get(client, build_scrapedo_url(url, store_id, zip_code, super_proxy=attempt > 1))
            if r.status_code == 200:
                return {"status": "success", "html": r.text}
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 404):
                break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        await asyncio.sleep(2 * attempt)
    return {"status": "failed", "error": last_err}


# ───────────────────────── request 2: store-wise product (plugin) ─────────────────────────
def build_plugin_pdp_url(item_id: str, store_id: str, zip_code: str) -> str:
    product_url = f"https://www.homedepot.com/p/-/{item_id}"   # guide: /p/-/<itemId> chalta hai
    return (f"{PLUGIN_PDP}?token={settings.scrapedo_token}"
            f"&url={quote(product_url, safe='')}&storeid={store_id}&zipcode={zip_code}")


async def fetch_store_product(item_id, store_id, zip_code, client) -> dict:
    """Plugin /pdp -> HomeDepot ka product object (store price + stock). 400/404 pe retry nahi."""
    last_err = "unknown error"
    for attempt in range(1, settings.retries + 1):
        try:
            r = await sd_get(client, build_plugin_pdp_url(item_id, store_id, zip_code))
            if r.status_code == 200:
                prod = r.json()
                if isinstance(prod, dict) and isinstance(prod.get("data"), dict) and prod["data"].get("product"):
                    prod = prod["data"]["product"]
                return {"status": "success", "product": prod}
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 404):
                return {"status": "failed", "error": last_err, "code": r.status_code}
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        await asyncio.sleep(2 * attempt)   # 502 "homedepot pdp failed" -> safe to retry, charge nahi
    return {"status": "failed", "error": last_err, "code": 502}


# ───────────────────────── store name / zip / hours ─────────────────────────
def build_scrapedo_get_url(target_url: str) -> str:
    return f"{SCRAPEDO}?token={settings.scrapedo_token}&url={quote(target_url, safe='')}&geoCode=us"


async def lookup_store(store_id: str, client) -> dict | None:
    """StoreSearchServices se store object. Fail ho to None (non-fatal)."""
    if store_id in STORE_CACHE:
        return STORE_CACHE[store_id]
    url = f"{STORESEARCH_URL}?storeid={store_id}&type=json"
    for attempt in range(1, settings.retries + 1):
        try:
            r = await sd_get(client, build_scrapedo_get_url(url))
            if r.status_code == 200:
                stores = (r.json() or {}).get("stores") or []
                if stores:
                    STORE_CACHE[store_id] = stores[0]
                    return stores[0]
                return None
        except Exception:  # noqa: BLE001
            pass
        await asyncio.sleep(2 * attempt)
    return None


# ───────────────────────── master JSON format (parse_pdp) ─────────────────────────
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

    # ── Fallback: kuch pages (jaise /pep/) me JSON-LD nahi hota -> Apollo state se bharo ──
    if not p:
        ident = prod_node.get("identifiers") or {}
        brand_a = ident.get("brandName") or ""
        name_a = ident.get("productLabel") or ""
        if brand_a and name_a.lower().startswith(brand_a.lower()):
            name_a = name_a[len(brand_a):].lstrip(" -:,|").strip()
        imgs = []
        for im in (media_node.get("images") or []):
            u = (im.get("url") or "").replace("<SIZE>", "1000")
            if u and u not in imgs:
                imgs.append(u)
        crumbs = [b.get("label") for b in ((prod_node.get("taxonomy") or {}).get("breadCrumbs") or []) if b.get("label")]
        rr = ((prod_node.get("reviews") or {}).get("ratingsReviews") or {})
        val = pricing_node.get("value")
        orig = pricing_node.get("original")
        canon = ident.get("canonicalUrl")
        data.update({
            "Product URL": data["Product URL"] if canonical_link else (f"https://www.homedepot.com{canon}" if canon else url),
            "Product Name": data["Product Name"] or name_a,
            "Product ID": data["Product ID"] or ident.get("itemId") or "",
            "Brand": data["Brand"] or brand_a,
            "SKU": data["SKU"] or ident.get("storeSkuNumber"),
            "Model": data["Model"] or ident.get("modelNumber"),
            "Image URL": data["Image URL"] or "\n".join(imgs),
            "Description": data["Description"] or details_node.get("description"),
            "Category": data["Category"] or (crumbs[-1] if crumbs else ""),
            "Breadcrumb": data["Breadcrumb"] or " > ".join(crumbs),
            "Sale Price": data["Sale Price"] or (float(val) if val is not None else 0.0),
            "Full Price": (orig if orig is not None else (float(val) if val is not None else data["Full Price"])),
            "Currency": "USD",
            "Rating": data["Rating"] or rr.get("averageRating"),
            "ReviewCount": data["ReviewCount"] or rr.get("totalReviews"),
            "UPC": data["UPC"] or ident.get("upcGtin13", ""),
            "Model Number": data["Model Number"] or ident.get("modelNumber", ""),
            "Product Type": data["Product Type"] or ident.get("productType", ""),
        })

    if not data["Product Name"] and not data["Sale Price"]:
        raise ValueError("Parsing failed: page has no product data (blocked or layout changed)")
    return data
    # return html


# ───────────────────────── plugin data -> master JSON ─────────────────────────
def _dump_js_safe(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _pickup_location(prod: dict) -> dict:
    for opt in ((prod.get("fulfillment") or {}).get("fulfillmentOptions") or []):
        if opt.get("type") != "pickup":
            continue
        for svc in opt.get("services") or []:
            if svc.get("type") != "bopis":
                continue
            locs = svc.get("locations") or []
            for loc in locs:
                if loc.get("isAnchor"):
                    return loc | {"_fulfillable": opt.get("fulfillable")}
            if locs:
                return locs[0] | {"_fulfillable": opt.get("fulfillable")}
    return {}


def _delivery_service(prod: dict, svc_type: str) -> dict:
    for opt in ((prod.get("fulfillment") or {}).get("fulfillmentOptions") or []):
        for svc in opt.get("services") or []:
            if svc.get("type") == svc_type:
                return svc
    return {}


def apply_store_product(data: dict, prod: dict) -> dict:
    """Plugin ke store-wise values master JSON me (price, clearance, stock, pickup, delivery)."""
    pr = prod.get("pricing") or {}
    cl = pr.get("clearance") or {}
    avail = prod.get("availabilityType") or {}
    pick = _pickup_location(prod)
    inv = pick.get("inventory") or {}
    sth = _delivery_service(prod, "sth")
    sth_inv = ((sth.get("locations") or [{}])[0].get("inventory") or {})
    exp = _delivery_service(prod, "express delivery")
    promo = pr.get("promotion") or {}

    if pr.get("value") is not None:
        data["Sale Price"] = pr["value"]
        data["Full Price"] = pr["original"] if pr.get("original") is not None else pr["value"]
    if promo:
        data["Promo Type"] = promo.get("type", "")
        data["Promo Dollar Off"] = promo.get("dollarOff", "")
        data["Promo Percent Off"] = promo.get("percentageOff", "")
        dates = promo.get("dates") or {}
        data["Promo Start"], data["Promo End"] = dates.get("start", ""), dates.get("end", "")
    if avail:
        data["Availability Type"] = avail.get("type", "")
        data["Is Discontinued"] = avail.get("discontinued", "")

    # Stock = store pe on-hand (pickup). Item store me nahi bikta to online buyable se.
    if inv:
        data["Stock"] = "InStock" if inv.get("isInStock") else "OutOfStock"
    elif avail.get("buyable") is not None:
        data["Stock"] = "InStock" if avail.get("buyable") else "OutOfStock"

    # Naye store-level fields
    ful = prod.get("fulfillment") or {}
    if not ful.get("fulfillmentOptions") and not pick:
        data["Store Availability"] = "NotSoldInStore"     # online-only item, store me stock hota hi nahi
    elif inv:
        data["Store Availability"] = "InStock" if inv.get("isInStock") else "OutOfStock"
    else:
        data["Store Availability"] = "Unavailable"
    data["Store Price"] = pr.get("value")
    data["Clearance Price"] = cl.get("value")
    data["Clearance Dollar Off"] = cl.get("dollarOff")
    data["Clearance Percent Off"] = cl.get("percentageOff")
    data["Store Quantity"] = inv.get("quantity")
    data["Pickup Available"] = pick.get("_fulfillable")
    data["Ship To Home Quantity"] = sth_inv.get("quantity")
    data["Ship To Home Date"] = (sth.get("deliveryDates") or {}).get("startDate")
    data["Express Delivery Date"] = (exp.get("deliveryDates") or {}).get("startDate")
    data["Express Delivery Charge"] = exp.get("deliveryCharge")
    data["Badges"] = [b.get("label") or b.get("name") for b in (prod.get("badges") or [])]
    return data


def master_from_plugin(prod: dict, url: str) -> dict:
    """Page HTML na mile to master JSON seedha plugin ke product object se banao."""
    ident = prod.get("identifiers") or {}
    media = prod.get("media") or {}
    details = prod.get("details") or {}
    info = prod.get("info") or {}
    avail = prod.get("availabilityType") or {}
    brand = ident.get("brandName") or ""
    name = ident.get("productLabel") or ""
    if brand and name.lower().startswith(brand.lower()):
        name = name[len(brand):].lstrip(" -:,|").strip()
    imgs = []
    for im in media.get("images") or []:
        u = (im.get("url") or "").replace("<SIZE>", "1000")
        if u and u not in imgs:
            imgs.append(u)
    crumbs = [b.get("label") for b in ((prod.get("taxonomy") or {}).get("breadCrumbs") or []) if b.get("label")]
    rr = (prod.get("reviews") or {}).get("ratingsReviews") or {}
    key_features = {}
    for item in ((prod.get("keyProductFeatures") or {}).get("keyProductFeaturesItems") or []):
        for f in item.get("features") or []:
            key_features[f.get("name")] = f.get("value")
    specs = {}
    for g in prod.get("specificationGroup") or []:
        specs[g.get("specTitle")] = {s.get("specName"): s.get("specValue") for s in (g.get("specifications") or [])}
    canon = ident.get("canonicalUrl")
    pr = prod.get("pricing") or {}
    return {
        "_id": hashlib.md5(url.encode("utf-8")).hexdigest(),
        "item_id": prod.get("itemId") or ident.get("itemId"),
        "Product URL": f"https://www.homedepot.com{canon}" if canon else url,
        "Product Name": name,
        "Product ID": prod.get("itemId") or ident.get("itemId"),
        "Brand": brand,
        "SKU": ident.get("storeSkuNumber"),
        "Model": ident.get("modelNumber"),
        "Datetime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Image URL": "\n".join(imgs),
        "Description": details.get("description"),
        "Category": crumbs[-1] if crumbs else "",
        "Breadcrumb": " > ".join(crumbs),
        "Sale Price": pr.get("value"),
        "Full Price": pr.get("original") if pr.get("original") is not None else pr.get("value"),
        "Currency": "USD",
        "Rating": rr.get("averageRating"),
        "ReviewCount": rr.get("totalReviews"),
        "Availability": None,
        "Stock": "InStock" if avail.get("buyable") else "OutOfStock",
        "Product Type": ident.get("productType", ""),
        "Model Number": ident.get("modelNumber", ""),
        "UPC": ident.get("upc", "") or ident.get("upcGtin13", ""),
        "Availability Type": avail.get("type", ""),
        "Is Discontinued": avail.get("discontinued", ""),
        "Is Obsolete": avail.get("obsolete", ""),
        "Hide Price": info.get("hidePrice", ""),
        "Quantity Limit": info.get("quantityLimit", ""),
        "Returnable": info.get("returnable", ""),
        "Highlights": details.get("highlights") or [],
        "Key Features": key_features,
        "Specifications": specs,
        "seoDescription": (prod.get("seo") or {}).get("seoDescription", ""),
        "Videos": " | ".join(v.get("url", "") for v in (media.get("video") or []) if v.get("url")),
        "url": url,
    }


def minimal_html(prod: dict, data: dict) -> str:
    title = f'{data.get("Brand") or ""} {data.get("Product Name") or ""}'.strip()
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
            f"<title>{title.replace('<', '')}</title></head><body>"
            f'<script id="store-product-data" type="application/json">{_dump_js_safe(prod)}</script>'
            f'<script id="product-data" type="application/json">{_dump_js_safe(data)}</script>'
            "</body></html>")


# ───────────────────────── plugin data -> HTML ─────────────────────────
def _splice_json(html: str, marker_re: str, mutate) -> str:
    m = re.search(marker_re, html)
    if not m:
        return html
    try:
        start = html.find("{", m.end() - 1)
        obj, n = json.JSONDecoder().raw_decode(html[start:])
        mutate(obj)
        return html[:start] + _dump_js_safe(obj) + html[start + n:]
    except Exception:  # noqa: BLE001
        return html


def fill_html(html: str, item_id: str, prod: dict, data: dict, store: dict,
              store_id: str, zip_code: str) -> str:
    ck = lambda d: json.dumps(d, separators=(",", ":"))  # noqa: E731

    # 1) __APOLLO_STATE__ -> store-wise pricing / badges / fulfillment / availability
    def mut_apollo(ap: dict):
        node = ap.get(f"base-catalog-{item_id}") or next(
            (v for k, v in ap.items() if k.startswith("base-catalog-")), None)
        if node is None:
            return
        for k in [k for k in node if k.startswith(("pricing(", "badges(", "fulfillment("))]:
            del node[k]
        if prod.get("pricing") is not None:
            node["pricing(" + ck({"isBrandPricingPolicyCompliant": False, "storeId": store_id}) + ")"] = prod["pricing"]
        if prod.get("badges") is not None:
            node["badges(" + ck({"storeId": store_id}) + ")"] = prod["badges"]
        if prod.get("fulfillment") is not None:
            node["fulfillment(" + ck({"storeId": store_id, "zipCode": zip_code}) + ")"] = prod["fulfillment"]
        if prod.get("availabilityType"):
            node["availabilityType"] = prod["availabilityType"]

        # Recommendation section me isi item ka card (fbr-<item>) bhi requested store ka price dikhaye
        fbr = ap.get(f"fbr-{item_id}")
        if isinstance(fbr, dict) and prod.get("pricing") is not None:
            for k in [k for k in fbr if k.startswith(("pricing(", "badges("))]:
                del fbr[k]
            fbr["pricing(" + ck({"isBrandPricingPolicyCompliant": False, "storeId": store_id}) + ")"] = prod["pricing"]
            if prod.get("badges") is not None:
                fbr["badges(" + ck({"storeId": store_id}) + ")"] = prod["badges"]

    html = _splice_json(html, r"__APOLLO_STATE__\s*=\s*", mut_apollo)

    # 2) __APOLLO_OPERATIONS -> storeId
    def mut_ops(ops: dict):
        for op in ops.get("operations", []):
            v = op.get("variables")
            if isinstance(v, dict) and "storeId" in v:
                v["storeId"] = store_id

    html = _splice_json(html, r"__APOLLO_OPERATIONS\s*=\s*", mut_ops)

    # 3) __EXPERIENCE_CONTEXT__ -> store object + zips
    i = html.find("window.__EXPERIENCE_CONTEXT__")
    if i != -1:
        j = html.find("</script>", i)
        seg = html[i:j]
        new_store = {"storeHours": store.get("storeHours") or {}, "storeId": store_id,
                     "storeName": data.get("Store Name") or "", "storeZip": data.get("Store Zip") or ""}
        m = re.search(r'"store"\s*:\s*\{', seg)
        if m:
            try:
                s = m.end() - 1
                _, n = json.JSONDecoder().raw_decode(seg[s:])
                seg = seg[:s] + _dump_js_safe(new_store) + seg[s + n:]
            except Exception:  # noqa: BLE001
                pass

        def sub(text, key, val):
            # "key": "..."  ya  "key": undefined/null  -> "key": "val"
            return re.sub(rf'("{key}"\s*:\s*)(?:"[^"]*"|undefined|null)',
                          lambda mm: mm.group(1) + json.dumps(val), text)

        if data.get("Store Zip"):
            seg = sub(seg, "localStoreZip", data["Store Zip"])
        seg = sub(seg, "deliveryZip", zip_code)
        html = html[:i] + seg + html[j:]

    # 4) plugin ka poora JSON + master JSON
    blocks = (f'<script id="store-product-data" type="application/json">{_dump_js_safe(prod)}</script>'
              f'<script id="product-data" type="application/json">{_dump_js_safe(data)}</script>')
    k = html.lower().rfind("</body>")
    return (html[:k] + blocks + html[k:]) if k != -1 else (html + blocks)


def _append_product_data(html: str, data: dict) -> str:
    block = f'<script id="product-data" type="application/json">{_dump_js_safe(data)}</script>'
    k = html.lower().rfind("</body>")
    return (html[:k] + block + html[k:]) if k != -1 else (html + block)


# ───────────────────────── main entry ─────────────────────────
async def scrape_pdp(url: str, store_id: str | None = None, zip_code: str | None = None,
                     client: httpx.AsyncClient | None = None) -> dict:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        m = ITEM_ID_RE.search(url)
        item_id = m.group(1) if m else None

        # store / zip ke bina: sirf normal PDP
        if not store_id:
            pdp = await fetch_pdp_html(url, None, zip_code, client)
            if pdp["status"] != "success":
                return {"url": url, "status": "failed", "error": pdp["error"]}
            data = await asyncio.to_thread(parse_pdp, pdp["html"], url)
            return {"url": url, "status": "success 200", "data": _append_product_data(pdp["html"], data),
                    "stock_status": "ok (no store)"}

        if not zip_code:
            return {"url": url, "status": "failed", "error": "zip_code is required with store_id"}
        if not item_id:
            return {"url": url, "status": "failed", "error": "item id not found in url"}

        sid_num = str(int(store_id))      # "06175" -> "6175" (requests ke liye)
        sid_out = sid_num.zfill(4)        # "910" -> "0910" (output ke liye)

        pdp, sp, store = await asyncio.gather(
            fetch_pdp_html(url, sid_num, zip_code, client),
            fetch_store_product(item_id, sid_num, zip_code, client),
            lookup_store(sid_num, client),
        )

        if sp["status"] != "success":
            if sp.get("code") == 400:
                return {"url": url, "status": "failed", "error": f"invalid store_id / zip_code: {sp['error']}"}
            if sp.get("code") == 404:
                return {"url": url, "status": "failed", "error": "product not found on HomeDepot"}
            return {"url": url, "status": "failed", "error": f"store data failed: {sp['error']}"}
        prod = sp["product"]
        page_ok = pdp["status"] == "success"
        data = None
        if page_ok:
            try:
                data = await asyncio.to_thread(parse_pdp, pdp["html"], url)
            except Exception:  # noqa: BLE001
                page_ok = False
        if not page_ok:
            # Page HTML nahi mila (ROTATION_FAILED / block) -> plugin ke data se hi response
            data = master_from_plugin(prod, url)

        pick = _pickup_location(prod)
        addr = (store or {}).get("address") or {}
        data["Store ID"] = sid_out
        data["Store Name"] = (store or {}).get("name") or pick.get("storeName") or ""
        data["Store Zip"] = str(addr.get("postalCode") or "")[:5]
        data["Zip Code"] = zip_code
        data = apply_store_product(data, prod)

        if page_ok:
            html = fill_html(pdp["html"], item_id, prod, data, store or {}, sid_out, zip_code)
        else:
            html = minimal_html(prod, data)
        status = (f"ok (store {sid_out} {data['Store Name']} | price {data.get('Store Price')} "
                  f"| qty {data.get('Store Quantity')}" + ("" if page_ok else " | page html failed, plugin only") + ")")
        return {"url": url, "status": "success 200", "data": html, "stock_status": status}
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