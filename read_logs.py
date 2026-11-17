"""Local se API logs padho.
    python read_logs.py                 -> aaj ke last 50 logs
    python read_logs.py 2026_11_17      -> us din ke logs
    python read_logs.py 2026_11_17 502  -> us din ke sirf 502 wale
URI .env / env variable LOG_MONGO_URI se aata hai (code me password mat likho).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

from pymongo import MongoClient

URI = os.getenv("LOG_MONGO_URI")
DB = os.getenv("LOG_MONGO_DB", "Homedepot_API_logs")
IST = timezone(timedelta(hours=5, minutes=30))

day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(IST).strftime("%Y_%m_%d")
status = int(sys.argv[2]) if len(sys.argv) > 2 else None

col = MongoClient(URI, serverSelectionTimeoutMS=5000)[DB][day]
flt = {"status": status} if status else {}
print(f"{DB}.{day}: total {col.count_documents({})}, success {col.count_documents({'success': True})}, "
      f"failed {col.count_documents({'success': False})}\n")
for d in col.find(flt).sort("ts", -1).limit(50):
    print(f'{d.get("ts_ist")} | {d.get("status")} | {d.get("duration_ms")}ms | '
          f'pid={d.get("product_id")} store={d.get("store_id")} zip={d.get("zip_code")} | '
          f'{d.get("stock_status") or d.get("error") or ""} | ip={d.get("ip")}')
