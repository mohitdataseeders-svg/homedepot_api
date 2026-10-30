import requests

product_url = "https://www.homedepot.com/p/Tzumi-SoundPlay-Open-Ear-Earbuds-30744HD/339509576"
product_id = "339509576"
store_id = "154"
zip_code = "30360"

url = f"https://homedepot-api.onrender.com/v1/homedepot/pdp/{product_id}?store_id={store_id}&zip_code={zip_code}"
params = {"store_id": store_id, "zip_code": zip_code}

r = requests.get(url, timeout=60)

print("status code:", r.status_code)
print("X-Stock-Status header:", r.headers.get("X-Stock-Status"))
print(r.text)


# # local_test.py  (project root se chalao: python local_test.py)
# import asyncio, re
# from scraper.homedepot_pdp import scrape_pdp
#
# async def main():
#     res = await scrape_pdp(
#         "https://www.homedepot.com/p/339509576", store_id="115", zip_code="30360"
#     )
#     print("status:", res["status"])
#     print("stock_status:", res.get("stock_status"))
#     print("warnings:", res.get("inject_warnings"))
#     html = res.get("data", "")
#     ctx = re.search(r'"storeId":"(\d+)","storeName":"([^"]*)","storeZip":"(\d*)"', html)
#     print("experience context store:", ctx.groups() if ctx else "NOT FOUND")
#     print("store-search block:", 'id="store-search-data"' in html)
#
# asyncio.run(main())


# -------------------------------------------------------------------------------------------------#

# test_graphql.py
# import json, httpx
# from urllib.parse import quote
# from config import settings
#
# URL = "https://apionline.homedepot.com/federation-gateway/graphql?opname=productClientOnlyProduct"
# payload = json.load(open("payload_from_browser.json"))   # browser wala exact body (query + variables)
# payload["variables"].update({"itemId": "342938293", "storeId": "115", "zipCode": "30360"})
#
# headers = {  # browser cURL se saare headers yahan copy karo (cookie chhod ke try karo, phir cookie ke saath)
#     "content-type": "application/json",
#     "origin": "https://www.homedepot.com",
#     "referer": "https://www.homedepot.com/p/342938293",
#     "x-experience-name": "fusion-gm-pip-desktop",
#     "x-current-url": "/p/342938293",
#     "x-hd-dc": "origin",
#     "x-debug": "false",
#     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
# }
#
# sd = f"https://api.scrape.do/?token={settings.scrapedo_token}&url={quote(URL, safe='')}&geoCode=us&customHeaders=true"
# r = httpx.post(sd, json=payload, headers=headers, timeout=60)
# print(r.status_code)
# body = r.json()
# prod = (body.get("data") or {}).get("product")
# print("product mila:", bool(prod))
# print(json.dumps(body.get("errors") or body.get("error"), indent=2)[:2000])
# if prod:
#     loc = prod["fulfillment"]["fulfillmentOptions"][0]["services"][0]["locations"][0]
#     print(loc.get("locationId"), loc.get("storeName"), loc.get("inventory"))