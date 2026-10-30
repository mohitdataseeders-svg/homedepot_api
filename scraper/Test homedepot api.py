import requests

product_url = "https://www.homedepot.com/p/Tzumi-SoundPlay-Open-Ear-Earbuds-30744HD/339509576"
product_id = "339509576"
store_id = "0115"
zip_code = "30360"

url = f"https://homedepot-api.onrender.com/v1/homedepot/pdp/{product_id}?store_id={store_id}&zip_code={zip_code}"
params = {"store_id": store_id, "zip_code": zip_code}

r = requests.get(url, timeout=60)

print("status code:", r.status_code)
print("X-Stock-Status header:", r.headers.get("X-Stock-Status"))
print(r.text)