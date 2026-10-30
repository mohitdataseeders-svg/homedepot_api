"""HomeDepot PDP scraper.

GraphQL 206 de to naye proxy IP se retry (max 3 round, har round me full + lite parallel).

Har request pe sirf 2 calls (dono parallel, scrape.do se):
  1) PDP HTML                      -> www.homedepot.com/p/<id>
  2) GraphQL productClientOnlyProduct (storeId + zipCode ke saath)
                                   -> apionline.homedepot.com/federation-gateway/graphql

GraphQL ka store-wise data HTML me daala jaata hai:
  - __APOLLO_STATE__   : pricing / badges / fulfillment (stock) / availabilityType
  - __EXPERIENCE_CONTEXT__ : storeId / storeName / storeZip / localStoreZip / deliveryZip
  - __APOLLO_OPERATIONS    : storeId
  - </body> se pehle <script id="graphql-product-data"> me poora GraphQL response

Test:
    python -m scraper.homedepot_pdp https://www.homedepot.com/p/342938293 115 30360
"""
import asyncio
import json
import re
import sys
from urllib.parse import quote

import httpx

from config import settings

SCRAPEDO = "https://api.scrape.do/"
GRAPHQL_URL = "https://apionline.homedepot.com/federation-gateway/graphql?opname=productClientOnlyProduct"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
ITEM_ID_RE = re.compile(r"/(\d{6,})(?:[/?#]|$)")

# Browser wali exact query (bina trim kiye)
PRODUCT_QUERY = 'query productClientOnlyProduct($itemId: String!, $loyaltyMembershipInput: LoyaltyMembershipInput, $dataSource: String, $storeId: String, $isBrandPricingPolicyCompliant: Boolean, $zipCode: String, $skipInstallServices: Boolean = true, $quantity: Int, $skipFavoriteCount: Boolean = false, $skipSubscribeAndSave: Boolean = false, $configId: String, $skipPaintDetails: Boolean = true, $skipSpecificationGroup: Boolean = false, $skipKPF: Boolean = false) {\n  product(\n    itemId: $itemId\n    loyaltyMembershipInput: $loyaltyMembershipInput\n    dataSource: $dataSource\n  ) {\n    dataSources\n    identifiers {\n      productType\n      storeSkuNumber\n      brandName\n      productLabel\n      canonicalUrl\n      itemId\n      parentId\n      omsThdSku\n      specialOrderSku\n      isSuperSku\n      sampleId\n      brandMainPageUrl\n      skuClassification\n      modelNumber\n      toolRentalSkuNumber\n      rentalCategory\n      rentalSubCategory\n      upc\n      upcGtin13\n      roomVOEnabled\n      __typename\n    }\n    availabilityType {\n      type\n      discontinued\n      status\n      buyable\n      __typename\n    }\n    media {\n      images {\n        url\n        type\n        subType\n        sizes\n        hotspots {\n          coordinate {\n            xCoordinate\n            yCoordinate\n            __typename\n          }\n          omsIDs\n          __typename\n        }\n        ocrHotspots {\n          coordinate {\n            xCoordinate\n            yCoordinate\n            __typename\n          }\n          omsIDs\n          __typename\n        }\n        altText\n        __typename\n      }\n      video {\n        link {\n          text\n          url\n          __typename\n        }\n        shortDescription\n        title\n        type\n        videoId\n        videoStill\n        url\n        thumbnail\n        longDescription\n        uploadDate\n        dateModified\n        __typename\n      }\n      threeSixty {\n        id\n        url\n        __typename\n      }\n      augmentedRealityLink {\n        usdz\n        image\n        __typename\n      }\n      __typename\n    }\n    info {\n      bathRenovation\n      label\n      isSponsored\n      sponsoredMetadata {\n        campaignId\n        placementId\n        slotId\n        sponsoredId\n        trackSource\n        __typename\n      }\n      sponsoredBeacon {\n        onClickBeacon\n        onViewBeacon\n        onClickBeacons\n        onViewBeacons\n        __typename\n      }\n      productSubType {\n        name\n        link\n        __typename\n      }\n      augmentedReality\n      globalCustomConfigurator {\n        customExperience\n        customButtonText\n        customDescription\n        customExperienceUrl\n        customTitle\n        customPosition\n        __typename\n      }\n      isLiveGoodsProduct\n      hidePrice\n      ecoRebate\n      quantityLimit\n      categoryHierarchy\n      sskMin\n      sskMax\n      unitOfMeasureCoverage\n      wasMaxPriceRange\n      wasMinPriceRange\n      movingCalculatorEligible\n      gccExperienceOmsId\n      dotComColorEligible\n      forProfessionalUseOnly\n      replacementOMSID\n      hasVisuallySimilar\n      returnable\n      isBuryProduct\n      isGenericProduct\n      classNumber\n      hasSubscription\n      productDepartment\n      isInStoreReturnMessageEligible\n      paintBrand\n      paintFamily\n      recommendationFlags {\n        packages\n        frequentlyBoughtTogether\n        bundles\n        visualNavigation\n        pipCollections\n        ACC\n        collections\n        batItems\n        __typename\n      }\n      minimumOrderQuantity\n      projectCalculatorEligible\n      subClassNumber\n      protectionPlanSku\n      eligibleProtectionPlanSkus\n      hasServiceAddOns\n      consultationType\n      pipCalculator {\n        coverageUnits\n        display\n        publisher\n        toggle\n        defaultAdditionalCoverage\n        additionalCoveragePercentage\n        __typename\n      }\n      __typename\n    }\n    itemId\n    taxonomy {\n      breadCrumbs {\n        browseUrl\n        creativeIconUrl\n        deselectUrl\n        dimensionName\n        label\n        refinementKey\n        url\n        __typename\n      }\n      brandLinkUrl\n      __typename\n    }\n    pricing(\n      storeId: $storeId\n      isBrandPricingPolicyCompliant: $isBrandPricingPolicyCompliant\n    ) {\n      value\n      unitOfMeasure\n      alternatePriceDisplay\n      message\n      original\n      mapAboveOriginalPrice\n      promotion {\n        dollarOff\n        type\n        description {\n          shortDesc\n          longDesc\n          __typename\n        }\n        percentageOff\n        promotionTag\n        savingsCenter\n        savingsCenterPromos\n        specialBuySavings\n        specialBuyDollarOff\n        specialBuyPercentageOff\n        dates {\n          end\n          start\n          __typename\n        }\n        experienceTag\n        subExperienceTag\n        __typename\n      }\n      alternate {\n        bulk {\n          pricePerUnit\n          thresholdQuantity\n          value\n          __typename\n        }\n        unit {\n          caseUnitOfMeasure\n          unitsOriginalPrice\n          unitsPerCase\n          value\n          __typename\n        }\n        __typename\n      }\n      mapDetail {\n        percentageOff\n        dollarOff\n        effectiveMap\n        mapPolicy\n        mapOriginalPriceViolation\n        mapSpecialPriceViolation\n        __typename\n      }\n      preferredPriceFlag\n      specialBuy\n      clearance {\n        value\n        dollarOff\n        percentageOff\n        unitsClearancePrice\n        __typename\n      }\n      conditionalPromotions {\n        experienceTag\n        promotionId\n        skuItemGroup\n        promotionTags\n        eligibilityCriteria {\n          itemGroup\n          minThresholdVal\n          thresholdType\n          minPurchaseAmount\n          minPurchaseQuantity\n          relatedSkusCount\n          omsSkus\n          __typename\n        }\n        reward {\n          tiers {\n            minThresholdVal\n            thresholdType\n            rewardVal\n            rewardType\n            rewardLevel\n            maxAllowedRewardAmount\n            minPurchaseAmount\n            minPurchaseQuantity\n            rewardPercent\n            rewardAmountPerOrder\n            rewardAmountPerItem\n            rewardFixedPrice\n            maxPurchaseQuantity\n            __typename\n          }\n          __typename\n        }\n        dates {\n          start\n          end\n          __typename\n        }\n        description {\n          shortDesc\n          longDesc\n          __typename\n        }\n        subExperienceTag\n        nvalues\n        brandRefinementId\n        __typename\n      }\n      __typename\n    }\n    dataSource\n    badges(storeId: $storeId) {\n      name\n      label\n      endDate\n      color\n      creativeImageUrl\n      message\n      timerDuration\n      timer {\n        timeBombThreshold\n        daysLeftThreshold\n        dateDisplayThreshold\n        message\n        __typename\n      }\n      __typename\n    }\n    reviews {\n      ratingsReviews {\n        totalReviews\n        averageRating\n        __typename\n      }\n      __typename\n    }\n    installServices(storeId: $storeId, zipCode: $zipCode) @skip(if: $skipInstallServices) {\n      scheduleAMeasure\n      gccCarpetDesignAndOrderEligible\n      __typename\n    }\n    fulfillment(storeId: $storeId, zipCode: $zipCode, quantity: $quantity) {\n      fulfillmentOptions {\n        services {\n          type\n          locations {\n            isAnchor\n            inventory {\n              quantity\n              isOutOfStock\n              isInStock\n              isLimitedQuantity\n              isUnavailable\n              maxAllowedBopisQty\n              minAllowedBopisQty\n              __typename\n            }\n            curbsidePickupFlag\n            isBuyInStoreCheckNearBy\n            distance\n            locationId\n            state\n            storeName\n            storePhone\n            type\n            storeTimeZone\n            __typename\n          }\n          deliveryTimeline\n          deliveryDates {\n            startDate\n            endDate\n            __typename\n          }\n          deliveryCharge\n          dynamicEta {\n            hours\n            minutes\n            __typename\n          }\n          hasFreeShipping\n          freeDeliveryThreshold\n          totalCharge\n          deliveryMessage\n          earliestDeliveryDate\n          shipFromFastestLocation\n          optimalFulfillment\n          ffaFallbackMode\n          hasSameDayCarDelivery\n          shipFromFastestLocationType\n          sameDayDeliveryCharge\n          __typename\n        }\n        type\n        fulfillable\n        priorityDeliveryOptions {\n          date\n          timeline\n          totalCharge\n          type\n          __typename\n        }\n        programInclusions {\n          description\n          threshold\n          __typename\n        }\n        __typename\n      }\n      anchorStoreStatus\n      anchorStoreStatusType\n      backordered\n      backorderedShipDate\n      bossExcludedShipStates\n      excludedShipStates\n      seasonStatusEligible\n      onlineStoreStatus\n      onlineStoreStatusType\n      sthExcludedShipState\n      fulfillmentBundleMessage\n      bundleComponents {\n        id\n        quantity\n        fulfillmentOptions {\n          type\n          availableFulfillmentTypes\n          __typename\n        }\n        __typename\n      }\n      fallbackMode\n      bossExcludedShipState\n      apoFpoEligible\n      inStoreAssemblyEligible\n      bodfsAssemblyEligible\n      __typename\n    }\n    details {\n      collection {\n        name\n        url\n        collectionId\n        __typename\n      }\n      description\n      highlights\n      installation {\n        serviceType\n        leadGenUrl\n        __typename\n      }\n      __typename\n    }\n    favoriteDetail @skip(if: $skipFavoriteCount) {\n      count\n      __typename\n    }\n    subscription @skip(if: $skipSubscribeAndSave) {\n      defaultfrequency\n      discountPercentage\n      subscriptionEnabled\n      __typename\n    }\n    bundleItems {\n      id\n      quantity\n      __typename\n    }\n    paintDetails(configId: $configId, storeId: $storeId) @skip(if: $skipPaintDetails) {\n      brandLogo\n      colorType\n      rgb {\n        red\n        green\n        blue\n        __typename\n      }\n      colorDisplayName\n      __typename\n    }\n    specificationGroup @skip(if: $skipSpecificationGroup) {\n      specifications {\n        specName\n        specValue\n        __typename\n      }\n      specTitle\n      __typename\n    }\n    seo {\n      seoKeywords\n      seoDescription\n      __typename\n    }\n    keyProductFeatures @skip(if: $skipKPF) {\n      keyProductFeaturesItems {\n        features {\n          name\n          refinementId\n          refinementUrl\n          value\n          __typename\n        }\n        __typename\n      }\n      __typename\n    }\n    bundleFlag\n    sizeAndFitDetail {\n      attributeGroups {\n        attributes {\n          attributeName\n          dimensions\n          __typename\n        }\n        dimensionLabel\n        productType\n        __typename\n      }\n      __typename\n    }\n    bundleSpecificationDetails(storeId: $storeId, zipCode: $zipCode) {\n      parents {\n        parentId\n        __typename\n      }\n      type\n      experienceType\n      __typename\n    }\n    seoDescription\n    __typename\n  }\n}'


# ───────────────────────── scrape.do URLs ─────────────────────────
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


# ───────────────────────── request 1: PDP HTML ─────────────────────────
async def fetch_pdp_html(url, store_id, zip_code, client) -> dict:
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


# ───────────────────────── request 2: GraphQL (stock/store/zip) ─────────────────────────
# Chhoti query: sirf pricing / badges / availability / fulfillment (stock).
# Ye pehle local pe chal chuki hai ("injected" aaya tha).
STOCK_QUERY_LITE = 'query productClientOnlyProduct($itemId: String!, $loyaltyMembershipInput: LoyaltyMembershipInput, $dataSource: String, $storeId: String, $isBrandPricingPolicyCompliant: Boolean, $zipCode: String, $quantity: Int) {\n  product(itemId: $itemId, loyaltyMembershipInput: $loyaltyMembershipInput, dataSource: $dataSource) {\n    itemId\n    availabilityType {\n      type\n      discontinued\n      status\n      buyable\n      __typename\n    }\n    pricing(\n      storeId: $storeId\n      isBrandPricingPolicyCompliant: $isBrandPricingPolicyCompliant\n    ) {\n      value\n      unitOfMeasure\n      alternatePriceDisplay\n      message\n      original\n      mapAboveOriginalPrice\n      promotion {\n        dollarOff\n        type\n        description {\n          shortDesc\n          longDesc\n          __typename\n        }\n        percentageOff\n        promotionTag\n        savingsCenter\n        savingsCenterPromos\n        specialBuySavings\n        specialBuyDollarOff\n        specialBuyPercentageOff\n        dates {\n          end\n          start\n          __typename\n        }\n        experienceTag\n        subExperienceTag\n        __typename\n      }\n      alternate {\n        bulk {\n          pricePerUnit\n          thresholdQuantity\n          value\n          __typename\n        }\n        unit {\n          caseUnitOfMeasure\n          unitsOriginalPrice\n          unitsPerCase\n          value\n          __typename\n        }\n        __typename\n      }\n      mapDetail {\n        percentageOff\n        dollarOff\n        effectiveMap\n        mapPolicy\n        mapOriginalPriceViolation\n        mapSpecialPriceViolation\n        __typename\n      }\n      preferredPriceFlag\n      specialBuy\n      clearance {\n        value\n        dollarOff\n        percentageOff\n        unitsClearancePrice\n        __typename\n      }\n      conditionalPromotions {\n        experienceTag\n        promotionId\n        skuItemGroup\n        promotionTags\n        eligibilityCriteria {\n          itemGroup\n          minThresholdVal\n          thresholdType\n          minPurchaseAmount\n          minPurchaseQuantity\n          relatedSkusCount\n          omsSkus\n          __typename\n        }\n        reward {\n          tiers {\n            minThresholdVal\n            thresholdType\n            rewardVal\n            rewardType\n            rewardLevel\n            maxAllowedRewardAmount\n            minPurchaseAmount\n            minPurchaseQuantity\n            rewardPercent\n            rewardAmountPerOrder\n            rewardAmountPerItem\n            rewardFixedPrice\n            maxPurchaseQuantity\n            __typename\n          }\n          __typename\n        }\n        dates {\n          start\n          end\n          __typename\n        }\n        description {\n          shortDesc\n          longDesc\n          __typename\n        }\n        subExperienceTag\n        nvalues\n        brandRefinementId\n        __typename\n      }\n      __typename\n    }\n    badges(storeId: $storeId) {\n      name\n      label\n      endDate\n      color\n      creativeImageUrl\n      message\n      timerDuration\n      timer {\n        timeBombThreshold\n        daysLeftThreshold\n        dateDisplayThreshold\n        message\n        __typename\n      }\n      __typename\n    }\n    fulfillment(storeId: $storeId, zipCode: $zipCode, quantity: $quantity) {\n      fulfillmentOptions {\n        services {\n          type\n          locations {\n            isAnchor\n            inventory {\n              quantity\n              isOutOfStock\n              isInStock\n              isLimitedQuantity\n              isUnavailable\n              maxAllowedBopisQty\n              minAllowedBopisQty\n              __typename\n            }\n            curbsidePickupFlag\n            isBuyInStoreCheckNearBy\n            distance\n            locationId\n            state\n            storeName\n            storePhone\n            type\n            storeTimeZone\n            __typename\n          }\n          deliveryTimeline\n          deliveryDates {\n            startDate\n            endDate\n            __typename\n          }\n          deliveryCharge\n          dynamicEta {\n            hours\n            minutes\n            __typename\n          }\n          hasFreeShipping\n          freeDeliveryThreshold\n          totalCharge\n          deliveryMessage\n          earliestDeliveryDate\n          shipFromFastestLocation\n          optimalFulfillment\n          ffaFallbackMode\n          hasSameDayCarDelivery\n          shipFromFastestLocationType\n          sameDayDeliveryCharge\n          __typename\n        }\n        type\n        fulfillable\n        priorityDeliveryOptions {\n          date\n          timeline\n          totalCharge\n          type\n          __typename\n        }\n        programInclusions {\n          description\n          threshold\n          __typename\n        }\n        __typename\n      }\n      anchorStoreStatus\n      anchorStoreStatusType\n      backordered\n      backorderedShipDate\n      bossExcludedShipStates\n      excludedShipStates\n      seasonStatusEligible\n      onlineStoreStatus\n      onlineStoreStatusType\n      sthExcludedShipState\n      fulfillmentBundleMessage\n      bundleComponents {\n        id\n        quantity\n        fulfillmentOptions {\n          type\n          availableFulfillmentTypes\n          __typename\n        }\n        __typename\n      }\n      fallbackMode\n      bossExcludedShipState\n      apoFpoEligible\n      inStoreAssemblyEligible\n      bodfsAssemblyEligible\n      __typename\n    }\n    __typename\n  }\n}'


def build_scrapedo_post_url() -> str:
    return (f"{SCRAPEDO}?token={settings.scrapedo_token}"
            f"&url={quote(GRAPHQL_URL, safe='')}&geoCode=us&customHeaders=true")


def _graphql_headers(item_id: str) -> dict:
    # Wahi minimal headers jo local pe pehle chal chuke hain ("injected" aaya tha)
    return {
        "content-type": "application/json",
        "accept": "*/*",
        "origin": "https://www.homedepot.com",
        "referer": "https://www.homedepot.com/",
        "x-experience-name": "fusion-gm-pip-desktop",
        "x-current-url": f"/p/{item_id}",
        "x-hd-dc": "origin",
        "x-debug": "false",
        "user-agent": UA,
    }


def _graphql_payload(query: str, item_id: str, store_id: str, zip_code: str | None) -> dict:
    variables = {
        "isBrandPricingPolicyCompliant": False,
        "itemId": item_id,
        "loyaltyMembershipInput": None,
        "storeId": store_id,
        "zipCode": zip_code,
    }
    if query is PRODUCT_QUERY:
        variables.update({
            "skipInstallServices": True, "skipFavoriteCount": False,
            "skipSubscribeAndSave": False, "skipPaintDetails": True,
            "skipSpecificationGroup": False, "skipKPF": False,
        })
    return {"operationName": "productClientOnlyProduct", "variables": variables, "query": query}


# HTTP 206 "Generic Errors API" proxy IP pe depend karta hai: kisi IP pe chalta hai,
# kisi pe nahi. scrape.do har request pe naya IP deta hai, isliye retry karte hain.
# Har round me 2 requests ek saath (full + lite) -> jo pehle sahi aaye wo use.
GRAPHQL_ROUNDS = 3


async def _graphql_once(name, item_id, store_id, zip_code, client) -> dict:
    query = PRODUCT_QUERY if name == "full" else STOCK_QUERY_LITE
    try:
        r = await client.post(build_scrapedo_post_url(), json=_graphql_payload(query, item_id, store_id, zip_code),
                              headers=_graphql_headers(item_id))
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = {}
        prod = (body.get("data") or {}).get("product")
        if prod and prod.get("fulfillment"):
            return {"status": "success", "body": body, "product": prod, "via": name}
        return {"status": "failed", "error": f"{name}: HTTP {r.status_code} {r.text[:80]}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": f"{name}: {type(e).__name__}: {e}"}


async def fetch_graphql(item_id, store_id, zip_code, client) -> dict:
    errors = []
    for rnd in range(1, GRAPHQL_ROUNDS + 1):
        tasks = [asyncio.create_task(_graphql_once(n, item_id, store_id, zip_code, client))
                 for n in ("full", "lite")]
        try:
            for fut in asyncio.as_completed(tasks):
                res = await fut
                if res["status"] == "success":
                    res["via"] += f" round {rnd}"
                    return res
                errors.append(f"r{rnd} {res['error']}")
        finally:
            for t in tasks:
                t.cancel()
    return {"status": "failed", "error": " | ".join(errors)}


# ───────────────────────── GraphQL data -> HTML ─────────────────────────
def _dump_js_safe(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def _splice_json(html: str, marker_re: str, mutate) -> str:
    """'window.X = {json}' dhoondo, mutate(obj) chalao, wapas usi jagah likho."""
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


def _store_from_graphql(prod: dict, store_id: str) -> dict:
    """Fulfillment me se requested store ki location (name/state/phone)."""
    for opt in (prod.get("fulfillment") or {}).get("fulfillmentOptions") or []:
        for svc in opt.get("services") or []:
            for loc in svc.get("locations") or []:
                if loc.get("type") == "store" and loc.get("storeName"):
                    return loc
    return {"locationId": store_id}


def apply_graphql_to_html(html: str, item_id: str, prod: dict, body: dict,
                          store_id: str, zip_code: str | None) -> str:
    loc = _store_from_graphql(prod, store_id)
    store_name = loc.get("storeName") or ""
    ck = lambda d: json.dumps(d, separators=(",", ":"))  # noqa: E731

    # 1) __APOLLO_STATE__ -> store-wise pricing / badges / fulfillment / availability
    def mut_apollo(ap: dict):
        node = ap.get(f"base-catalog-{item_id}")
        if node is None:
            return
        for k in [k for k in node if k.startswith(("pricing(", "badges(", "fulfillment("))]:
            del node[k]
        if prod.get("pricing") is not None:
            node["pricing(" + ck({"isBrandPricingPolicyCompliant": False, "storeId": store_id}) + ")"] = prod["pricing"]
        if prod.get("badges") is not None:
            node["badges(" + ck({"storeId": store_id}) + ")"] = prod["badges"]
        ful_args = {"storeId": store_id}
        if zip_code:
            ful_args["zipCode"] = zip_code
        node["fulfillment(" + ck(ful_args) + ")"] = prod["fulfillment"]
        if prod.get("availabilityType"):
            node["availabilityType"] = prod["availabilityType"]

    html = _splice_json(html, r"__APOLLO_STATE__\s*=\s*", mut_apollo)

    # 2) __APOLLO_OPERATIONS -> storeId
    def mut_ops(ops: dict):
        for op in ops.get("operations", []):
            v = op.get("variables")
            if isinstance(v, dict) and "storeId" in v:
                v["storeId"] = store_id

    html = _splice_json(html, r"__APOLLO_OPERATIONS\s*=\s*", mut_ops)

    # 3) __EXPERIENCE_CONTEXT__ -> store / zip
    i = html.find("window.__EXPERIENCE_CONTEXT__")
    if i != -1:
        j = html.find("</script>", i)
        seg = html[i:j]

        def sub(s, key, val):
            return re.sub(rf'("{key}"\s*:\s*")[^"]*(")', lambda m: m.group(1) + val + m.group(2), s)

        seg = sub(seg, "storeId", store_id)
        seg = sub(seg, "storeName", store_name)
        if zip_code:
            seg = sub(seg, "storeZip", zip_code)
            seg = sub(seg, "localStoreZip", zip_code)
            seg = sub(seg, "deliveryZip", zip_code)
        html = html[:i] + seg + html[j:]

    # 4) poora GraphQL response ek script tag me
    block = f'<script id="graphql-product-data" type="application/json">{_dump_js_safe(body)}</script>'
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

        m = ITEM_ID_RE.search(url)
        if not m:
            return {"url": url, "status": "failed", "error": "item id not found in url"}
        item_id = m.group(1)

        # 2 requests, parallel
        pdp, gql = await asyncio.gather(
            fetch_pdp_html(url, store_id, zip_code, client),
            fetch_graphql(item_id, store_id, zip_code, client),
        )

        if pdp["status"] != "success":
            return {"url": url, "status": "failed", "error": pdp["error"]}
        if gql["status"] != "success":
            return {"url": url, "status": "failed",
                    "error": f"graphql failed: {gql['error']}", "stock_status": "graphql failed"}

        html = apply_graphql_to_html(pdp["html"], item_id, gql["product"], gql["body"], store_id, zip_code)
        return {"url": url, "status": "success 200", "data": html, "stock_status": f"graphql injected ({gql['via']})"}
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