# HomeDepot PDP API

## Setup
```
pip install -r requirements.txt
cp .env.example .env      # fill SCRAPEDO_TOKEN and API_KEYS
```

## 1) Test scraper alone first
```
python -m scraper.homedepot_pdp "https://www.homedepot.com/p/.../123456789" 1234
```
Check the output fields; adjust `parse_pdp()` if needed.

## 2) Run API
```
uvicorn main:app --reload
```
Docs: http://localhost:8000/docs

## 3) Call
```
curl -X POST http://localhost:8000/v1/homedepot/pdp \
  -H "X-API-Key: key1" -H "Content-Type: application/json" \
  -d '{"urls": ["https://www.homedepot.com/p/.../123456789"], "store_id": "1234"}'
```

## Notes / TODO to verify
- Store cookie format in `build_scrapedo_url` (store based price).
- Parsing uses JSON-LD; add more fields (specs, bullets, variants) from page state as needed.
- If 100 URLs take too long, move to job mode (POST -> job_id -> GET result).
