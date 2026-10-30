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


STORESEARCH_URL = "https://www.homedepot.com/StoreSearchServices/v2/storesearch"


def build_scrapedo_get_url(target_url: str) -> str:
    params = f"token={settings.scrapedo_token}&url={quote(target_url, safe='')}&geoCode=us"
    return f"{SCRAPEDO}?{params}"


async def lookup_store(store_id: str, client: httpx.AsyncClient) -> dict | None:
    """StoreSearchServices se poora store object laata hai, jaisa tumne curl me dikhaya."""
    url = f"{STORESEARCH_URL}?storeid={store_id}&type=json"
    try:
        r = await client.get(build_scrapedo_get_url(url))
        if r.status_code != 200:
            return None
        stores = (r.json() or {}).get("stores") or []
        return stores[0] if stores else None   # pura raw object, sab fields ke saath
    except Exception:
        return None

def build_scrapedo_url(url: str, store_id: str | None, zip_code: str | None,
                       store_label: str = "") -> str:
    params = f"token={settings.scrapedo_token}&url={quote(url, safe='')}&geoCode=us"
    cookies = []
    if store_id:
        loc = {
            "WORKFLOW": "LOCALIZED_BY_STORE",
            "THD_LOCSTORE": f"{store_id}+{store_label}+",
            "THD_INTERNAL": "0",
            "THD_FORCE_LOC": "0",
        }
        if zip_code:
            loc["THD_STRFINDERZIP"] = zip_code
        cookies.append("THD_LOCALIZER=" + quote(json.dumps(loc, separators=(",", ":")), safe=""))
        cookies.append(f"THD_PERSIST=C4%3D{store_id}%2B%2B%3BC4_EXP%3D9999999999")
    if zip_code:
        cookies.append(f"DELIVERY_ZIP={zip_code}")
        cookies.append("DELIVERY_ZIP_TYPE=USER")
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

GRAPHQL_URL = (
    "https://apionline.homedepot.com/federation-gateway/graphql"
    "?opname=productClientOnlyProduct"
)
GRAPHQL_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
)
ITEM_ID_RE = re.compile(r"/(\d{6,})(?:[/?#]|$)")

# Trimmed version of productClientOnlyProduct: sirf availabilityType, pricing,
# badges, fulfillment (original query ka same selection, baaki fields hata diye)
STOCK_QUERY = """query productClientOnlyProduct($itemId: String!, $loyaltyMembershipInput: LoyaltyMembershipInput, $dataSource: String, $storeId: String, $isBrandPricingPolicyCompliant: Boolean, $zipCode: String, $quantity: Int) {
  product(itemId: $itemId, loyaltyMembershipInput: $loyaltyMembershipInput, dataSource: $dataSource) {
    itemId
    availabilityType {
      type
      discontinued
      status
      buyable
      __typename
    }
    pricing(
      storeId: $storeId
      isBrandPricingPolicyCompliant: $isBrandPricingPolicyCompliant
    ) {
      value
      unitOfMeasure
      alternatePriceDisplay
      message
      original
      mapAboveOriginalPrice
      promotion {
        dollarOff
        type
        description {
          shortDesc
          longDesc
          __typename
        }
        percentageOff
        promotionTag
        savingsCenter
        savingsCenterPromos
        specialBuySavings
        specialBuyDollarOff
        specialBuyPercentageOff
        dates {
          end
          start
          __typename
        }
        experienceTag
        subExperienceTag
        __typename
      }
      alternate {
        bulk {
          pricePerUnit
          thresholdQuantity
          value
          __typename
        }
        unit {
          caseUnitOfMeasure
          unitsOriginalPrice
          unitsPerCase
          value
          __typename
        }
        __typename
      }
      mapDetail {
        percentageOff
        dollarOff
        effectiveMap
        mapPolicy
        mapOriginalPriceViolation
        mapSpecialPriceViolation
        __typename
      }
      preferredPriceFlag
      specialBuy
      clearance {
        value
        dollarOff
        percentageOff
        unitsClearancePrice
        __typename
      }
      conditionalPromotions {
        experienceTag
        promotionId
        skuItemGroup
        promotionTags
        eligibilityCriteria {
          itemGroup
          minThresholdVal
          thresholdType
          minPurchaseAmount
          minPurchaseQuantity
          relatedSkusCount
          omsSkus
          __typename
        }
        reward {
          tiers {
            minThresholdVal
            thresholdType
            rewardVal
            rewardType
            rewardLevel
            maxAllowedRewardAmount
            minPurchaseAmount
            minPurchaseQuantity
            rewardPercent
            rewardAmountPerOrder
            rewardAmountPerItem
            rewardFixedPrice
            maxPurchaseQuantity
            __typename
          }
          __typename
        }
        dates {
          start
          end
          __typename
        }
        description {
          shortDesc
          longDesc
          __typename
        }
        subExperienceTag
        nvalues
        brandRefinementId
        __typename
      }
      __typename
    }
    badges(storeId: $storeId) {
      name
      label
      endDate
      color
      creativeImageUrl
      message
      timerDuration
      timer {
        timeBombThreshold
        daysLeftThreshold
        dateDisplayThreshold
        message
        __typename
      }
      __typename
    }
    fulfillment(storeId: $storeId, zipCode: $zipCode, quantity: $quantity) {
      fulfillmentOptions {
        services {
          type
          locations {
            isAnchor
            inventory {
              quantity
              isOutOfStock
              isInStock
              isLimitedQuantity
              isUnavailable
              maxAllowedBopisQty
              minAllowedBopisQty
              __typename
            }
            curbsidePickupFlag
            isBuyInStoreCheckNearBy
            distance
            locationId
            state
            storeName
            storePhone
            type
            storeTimeZone
            __typename
          }
          deliveryTimeline
          deliveryDates {
            startDate
            endDate
            __typename
          }
          deliveryCharge
          dynamicEta {
            hours
            minutes
            __typename
          }
          hasFreeShipping
          freeDeliveryThreshold
          totalCharge
          deliveryMessage
          earliestDeliveryDate
          shipFromFastestLocation
          optimalFulfillment
          ffaFallbackMode
          hasSameDayCarDelivery
          shipFromFastestLocationType
          sameDayDeliveryCharge
          __typename
        }
        type
        fulfillable
        priorityDeliveryOptions {
          date
          timeline
          totalCharge
          type
          __typename
        }
        programInclusions {
          description
          threshold
          __typename
        }
        __typename
      }
      anchorStoreStatus
      anchorStoreStatusType
      backordered
      backorderedShipDate
      bossExcludedShipStates
      excludedShipStates
      seasonStatusEligible
      onlineStoreStatus
      onlineStoreStatusType
      sthExcludedShipState
      fulfillmentBundleMessage
      bundleComponents {
        id
        quantity
        fulfillmentOptions {
          type
          availableFulfillmentTypes
          __typename
        }
        __typename
      }
      fallbackMode
      bossExcludedShipState
      apoFpoEligible
      inStoreAssemblyEligible
      bodfsAssemblyEligible
      __typename
    }
    __typename
  }
}"""

# True => HTML me ek clean <script id="store-stock-data"> JSON block bhi jaata hai
INJECT_SUMMARY_BLOCK = True


def build_scrapedo_post_url() -> str:
    # customHeaders=true => neeche wale headers target tak forward hote hain
    # (agar block aaye to yaha "&super=true" add karke dekh)
    params = (
        f"token={settings.scrapedo_token}"
        f"&url={quote(GRAPHQL_URL, safe='')}&geoCode=us&customHeaders=true"
    )
    return f"{SCRAPEDO}?{params}"


async def fetch_stock(
    url: str, store_id: str, zip_code: str | None, client: httpx.AsyncClient
) -> dict:
    """2nd request. Never raises. -> {"status": "success", "product": {...}} / {"status": "failed", "error": ...}"""
    m = ITEM_ID_RE.search(url)
    if not m:
        return {"status": "failed", "error": "item id not found in url"}
    item_id = m.group(1)

    payload = {
        "operationName": "productClientOnlyProduct",
        "variables": {
            "itemId": item_id,
            "storeId": str(store_id),
            "zipCode": zip_code,
            "isBrandPricingPolicyCompliant": False,
            "loyaltyMembershipInput": None,
        },
        "query": STOCK_QUERY,
    }
    headers = {
        "content-type": "application/json",
        "accept": "*/*",
        "origin": "https://www.homedepot.com",
        "referer": "https://www.homedepot.com/",
        "x-experience-name": "fusion-gm-pip-desktop",
        "x-current-url": f"/p/{item_id}",
        "x-hd-dc": "origin",
        "x-debug": "false",
        "user-agent": GRAPHQL_UA,
    }

    last_err = "unknown error"
    for attempt in range(1, settings.retries + 1):
        try:
            r = await client.post(build_scrapedo_post_url(), json=payload, headers=headers)
            if r.status_code == 200:
                body = r.json()
                prod = (body.get("data") or {}).get("product")
                if prod and prod.get("fulfillment"):
                    return {"status": "success", "product": prod}
                # last_err = f"no product/fulfillment in response: {str(body.get('errors'))[:200]}"
                last_err = f"HTTP {r.status_code}: {r.text[:1000]}"
            else:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                if r.status_code in (400, 401, 404):
                    break
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        await asyncio.sleep(0.5 * attempt)
    return {"status": "failed", "error": last_err}


def summarize_stock(prod: dict, store_id: str, zip_code: str | None) -> dict:
    """Clean flat summary (HTML me <script id="store-stock-data"> ke liye)."""
    pr = prod.get("pricing") or {}
    ful = prod.get("fulfillment") or {}
    services, store_name, state, phone = [], "", "", ""
    for opt in ful.get("fulfillmentOptions") or []:
        for svc in opt.get("services") or []:
            locs = svc.get("locations") or []
            loc = locs[0] if locs else {}
            inv = loc.get("inventory") or {}
            if loc.get("storeName") and not store_name:
                store_name, state, phone = loc["storeName"], loc.get("state") or "", loc.get("storePhone") or ""
            services.append({
                "service": svc.get("type"),
                "fulfillable": opt.get("fulfillable"),
                "quantity": inv.get("quantity"),
                "in_stock": inv.get("isInStock"),
                "out_of_stock": inv.get("isOutOfStock"),
                "limited_quantity": inv.get("isLimitedQuantity"),
                "unavailable": inv.get("isUnavailable"),
                "delivery_timeline": svc.get("deliveryTimeline"),
                "delivery_charge": svc.get("deliveryCharge"),
            })
    pickup = next((s for s in services if s["service"] == "bopis"), None)
    qty = (pickup or (services[0] if services else {})).get("quantity")
    return {
        "store_id": str(store_id),
        "store_name": store_name,
        "store_state": state,
        "store_phone": phone,
        "zip_code": zip_code,
        "in_stock": any(bool(s["in_stock"]) for s in services),
        "quantity": qty,
        "buyable": (prod.get("availabilityType") or {}).get("buyable"),
        "price": pr.get("value"),
        "original_price": pr.get("original"),
        "services": services,
    }


def _dump_js_safe(obj) -> str:
    # compact JSON, "</script>" se HTML na toote
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")

def inject_store_search_block(html: str, store: dict) -> str:
    """StoreSearchServices ka poora response ek <script> tag ke andar HTML me daal deta hai."""
    block = f'<script id="store-search-data" type="application/json">{_dump_js_safe(store)}</script>'
    k = html.lower().rfind("</body>")
    return (html[:k] + block + html[k:]) if k != -1 else (html + block)


def _splice_json_assign(html: str, marker_re: str, mutate) -> tuple[str, bool]:
    """'window.X = {json}' dhoondho, json parse karo, mutate(obj) chalao, wapas usi jagah likho."""
    m = re.search(marker_re, html)
    if not m:
        return html, False
    start = html.find("{", m.end() - 1)
    obj, n = json.JSONDecoder().raw_decode(html[start:])
    mutate(obj)
    return html[:start] + _dump_js_safe(obj) + html[start + n:], True


def _find_product_ref(data):
    items = data if isinstance(data, list) else [data]
    for item in items:
        if isinstance(item, dict):
            if item.get("@type") == "Product":
                return item
            for g in item.get("@graph", []) or []:
                if isinstance(g, dict) and g.get("@type") == "Product":
                    return g
    return None


def inject_store_stock(
    html: str, url: str, prod: dict, store_id: str, zip_code: str | None
) -> tuple[str, list[str]]:
    """Random default store/stock data ki jagah 2nd request ka data daalta hai.
    Never raises: har step alag try/except me, problem hui to warnings me aati hai."""
    warnings: list[str] = []
    store_id = str(store_id)
    m = ITEM_ID_RE.search(url)
    item_id = m.group(1) if m else ""
    summary = summarize_stock(prod, store_id, zip_code)
    pr = prod.get("pricing") or {}

    # 1) Apollo state: pricing / badges / fulfillment / availabilityType (store-wise)
    def mut_apollo(ap: dict):
        node = ap.get(f"base-catalog-{item_id}") or next(
            (v for k, v in ap.items() if k.startswith("base-catalog-")), None
        )
        if node is None:
            raise ValueError("base-catalog node not found")
        for k in [k for k in node if k.startswith(("pricing(", "badges(", "fulfillment("))]:
            del node[k]
        ck = lambda d: json.dumps(d, separators=(",", ":"))  # noqa: E731
        ful_args = {"storeId": store_id}
        if zip_code:
            ful_args["zipCode"] = zip_code
        if prod.get("pricing") is not None:
            node["pricing(" + ck({"isBrandPricingPolicyCompliant": False, "storeId": store_id}) + ")"] = prod["pricing"]
        if prod.get("badges") is not None:
            node["badges(" + ck({"storeId": store_id}) + ")"] = prod["badges"]
        node["fulfillment(" + ck(ful_args) + ")"] = prod["fulfillment"]
        if prod.get("availabilityType"):
            node["availabilityType"] = prod["availabilityType"]

    try:
        html, ok = _splice_json_assign(html, r"__APOLLO_STATE__\s*=\s*", mut_apollo)
        if not ok:
            warnings.append("apollo state not found")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"apollo: {type(e).__name__}: {e}")

    # 2) __APOLLO_OPERATIONS: product query ke variables ka storeId
    def mut_ops(ops: dict):
        for op in ops.get("operations", []):
            v = op.get("variables")
            if isinstance(v, dict) and "storeId" in v:
                v["storeId"] = store_id

    try:
        html, _ = _splice_json_assign(html, r"__APOLLO_OPERATIONS\s*=\s*", mut_ops)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"apollo_operations: {type(e).__name__}: {e}")

    # 3) __EXPERIENCE_CONTEXT__ (JS literal, strict JSON nahi hai -> regex)
    try:
        i = html.find("window.__EXPERIENCE_CONTEXT__")
        if i != -1:
            j = html.find("</script>", i)
            seg = html[i:j]
            if zip_code:
                for key in ("deliveryZip", "localStoreZip"):
                    seg = re.sub(
                        rf'("{key}"\s*:\s*")[^"]*(")',
                        lambda m_: m_.group(1) + zip_code + m_.group(2),
                        seg,
                    )
            seg = re.sub(
                r'("storeId"\s*:\s*")\d+(",\s*"storeName"\s*:\s*")[^"]*(",\s*"storeZip"\s*:\s*")\d*(")',
                lambda m_: (
                    m_.group(1) + store_id + m_.group(2) + summary["store_name"]
                    + m_.group(3) + (zip_code or "") + m_.group(4)
                ),
                seg,
            )
            html = html[:i] + seg + html[j:]
        else:
            warnings.append("experience context not found")
    except Exception as e:  # noqa: BLE001
        warnings.append(f"experience_context: {type(e).__name__}: {e}")

    # 4) JSON-LD Product.offers: price / strikethrough price / validity / availability
    try:
        out, last = [], 0
        for jm in JSONLD_RE.finditer(html):
            try:
                data = json.loads(jm.group(1).strip())
            except json.JSONDecodeError:
                continue
            ref = _find_product_ref(data)
            if ref is None:
                continue
            offers = ref.get("offers")
            offer = offers[0] if isinstance(offers, list) and offers else offers
            if not isinstance(offer, dict):
                continue
            if pr.get("value") is not None:
                offer["price"] = pr["value"]
            spec = offer.get("priceSpecification")
            if isinstance(spec, dict) and pr.get("original") is not None:
                spec["price"] = pr["original"]
            end = ((pr.get("promotion") or {}).get("dates") or {}).get("end")
            if end:
                offer["priceValidUntil"] = end
            offer["availability"] = (
                "https://schema.org/InStock" if summary["in_stock"] else "https://schema.org/OutOfStock"
            )
            out.append(html[last:jm.start(1)])
            out.append(_dump_js_safe(data))
            last = jm.end(1)
        out.append(html[last:])
        html = "".join(out)
    except Exception as e:  # noqa: BLE001
        warnings.append(f"jsonld: {type(e).__name__}: {e}")

    # 5) clean summary block (stock ka HTML me koi native ghar nahi hai)
    if INJECT_SUMMARY_BLOCK:
        block = f'<script id="store-stock-data" type="application/json">{_dump_js_safe(summary)}</script>'
        k = html.lower().rfind("</body>")
        html = (html[:k] + block + html[k:]) if k != -1 else (html + block)

    return html, warnings


async def _fetch_pdp_html(url, store_id, zip_code, client) -> dict:
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


async def scrape_pdp(url, store_id=None, zip_code=None, client=None) -> dict:
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=settings.request_timeout)
    try:
        if not store_id:
            pdp = await _fetch_pdp_html(url, None, zip_code, client)
            if pdp["status"] != "success":
                return {"url": url, "status": "failed", "error": pdp["error"]}
            return {"url": url, "status": "success 200", "data": pdp["html"], "stock_status": "n/a"}

        # teeno calls ek saath -> total time = sabse slow wali call
        store_info, stock, pdp = await asyncio.gather(
            lookup_store(store_id, client),
            fetch_stock(url, store_id, zip_code, client),
            _fetch_pdp_html(url, store_id, zip_code, client),
        )

        if store_info is None:
            return {"url": url, "status": "failed",
                    "error": f"store_id {store_id} not found via StoreSearchServices"}
        if pdp["status"] != "success":
            return {"url": url, "status": "failed", "error": pdp["error"]}

        html, warnings = pdp["html"], []
        if stock["status"] == "success":
            html, warnings = inject_store_stock(html, url, stock["product"], store_id, zip_code)
            stock_status = "injected" + (" (with warnings)" if warnings else "")
        else:
            stock_status = f"stock failed: {stock['error'][:100]}"

        html = inject_store_search_block(html, store_info)
        return {"url": url, "status": "success 200", "data": html,
                "stock_status": stock_status, "inject_warnings": warnings}
    finally:
        if own_client:
            await client.aclose()


if __name__ == "__main__":
    out = asyncio.run(
        scrape_pdp(
            sys.argv[1],
            sys.argv[2] if len(sys.argv) > 2 else None,
            sys.argv[3] if len(sys.argv) > 3 else None,
        )
    )
    print(out.get("stock_status"), out.get("inject_warnings"), len(out.get("data", "")))