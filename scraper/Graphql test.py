"""Local check: GraphQL scrape.do se kitni baar chalta hai.
Project root se chalao:  python graphql_test.py
"""
import asyncio
import httpx
from scraper.homedepot_pdp import _graphql_once
from config import settings

async def main():
    async with httpx.AsyncClient(timeout=settings.request_timeout) as c:
        for i in range(1, 6):
            for name in ("full", "lite"):
                r = await _graphql_once(name, "342938293", "115", "30360", c)
                print(i, name, r["status"], r.get("error", "")[:90])

asyncio.run(main())