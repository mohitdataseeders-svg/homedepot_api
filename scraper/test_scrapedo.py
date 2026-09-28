import httpx
from config import settings

print("Token loaded:", bool(settings.scrapedo_token), "| length:", len(settings.scrapedo_token))

url = "https://www.homedepot.com/p/GE-4-5-cu-ft-Top-Load-Washer-in-White-with-Dual-Action-Agitator-and-Cold-Plus-Sanitize-with-Oxi-GTW485ASWWB/328425526"

# 1) bina extra params
r = httpx.get("https://api.scrape.do/", params={"token": settings.scrapedo_token, "url": url}, timeout=90)
print("PLAIN:", r.status_code, r.text[:300])
open("pdp_1.html", "w", encoding="utf-8").write(r.text)
print(r.status_code, len(r.text), "| ld+json:", "application/ld+json" in r.text)

# 2) geoCode + super
r = httpx.get("https://api.scrape.do/", params={"token": settings.scrapedo_token, "url": url, "geoCode": "us", "super": "true"}, timeout=90)
print("SUPER:", r.status_code, r.text[:300])
open("pdp_2.html", "w", encoding="utf-8").write(r.text)
print(r.status_code, len(r.text), "| ld+json:", "application/ld+json" in r.text)