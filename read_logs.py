"""Local se API logs padho.
    python read_logs.py                  -> aaj ke last 50 logs
    python read_logs.py 2026_11_17       -> us din ke logs
    python read_logs.py 2026_11_17 502   -> us din ke sirf 502 wale
URI aur DB project ke .env se aate hain (LOG_MONGO_URI, LOG_MONGO_DB).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv        # pip install python-dotenv
from pymongo import MongoClient

load_dotenv()

URI = os.getenv("LOG_MONGO_URI")
DB = os.getenv("LOG_MONGO_DB", "Homedepot_API_logs")
IST = timezone(timedelta(hours=5, minutes=30))

if not URI:
    sys.exit("LOG_MONGO_URI .env me nahi mila")

day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(IST).strftime("%Y_%m_%d")
status = int(sys.argv[2]) if len(sys.argv) > 2 else None

col = MongoClient(URI, serverSelectionTimeoutMS=5000)[DB][day]
flt = {"status": status} if status else {}
print(f"{DB}.{day}: total {col.count_documents({})}, success {col.count_documents({'success': True})}, "
      f"failed {col.count_documents({'success': False})}\n")
for d in col.find(flt).sort("ts", -1).limit(50):
    print(f'{d.get("ts_ist")} | {d.get("status")} | {d.get("duration_ms")}ms | '
          f'pid={d.get("product_id")} store={d.get("store_id")} zip={d.get("zip_code")} | '
          f'{d.get("error") or d.get("stock_status") or ""} | ip={d.get("ip")}')
