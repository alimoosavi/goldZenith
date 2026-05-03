import requests
import json

# ── Constants ─────────────────────────────────────────────────────────────────
RED_ENDPOINT   = "https://red.nibi.ir"   # e.g. "https://api.example.com"
AUTHORIZATION  = "eyJhbGciOiJBMjU2R0NNS1ciLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwiaXYiOiI1ck9pZ3N6bW1zVm9CYW92IiwidGFnIjoiNHkzWHBxZjM2WHN4YkFoNUFpS2FnQSJ9.hwY5pAcRXj9fQxWhhuSJQPyFkbg-drs04PeAs5el2x2ZowD2-xhFWiecz79tgbjrDh-G5utW9N919R7eyHMVTQ.5UXeika9EYmWFXZtw4BHrg.EFUCxIimQokPjNAjN1Vxihjuw1_WkehK_BcjW6do30S9W-xwXN8eu5Y8BMhG70u23DuI1kbc28sxh5QEFffLkfJIXo8-54K7pfraHGaE-F3-DFIuvJEEPAolnVNfwoCVGr872kFlfkU6cY6lEwxbPw6NiYIjchoR0PBWNxLn3t6yGMfUgdWTsTlknYhKkQjnvjJATg6NDHXskUFqUdRkjN3vOzsbHs9wIv3pudaw1A9ddjUbG5Gi1SrR4NlTtIviwxCZYP09nwR0fBZinkTTgvTpG2ybpX6dF_Odp9i-lowBuI4L6B24IaTlTiPFaVO9521r6N7xUkBUJjhzbnEk9IUElgxi_fkbZpSOIyXNxEqLSWMyTaUauK48WS__wWQbN9YiADySNSmADul-caRfu5RoXnBj3Orps3cO0ospQJIye9L8gkgSeFAKKP_AHXLzu-ygd_p5YeNHzA-Yc_Zoggsxmpc_oNBQzXIWfZD3geOnfBWs6bK-ke1n9f9O3Wpn9BAOqMv-ap8PhBcz6tT3StPIUhquP98TTtRwGhZRg0fLU5WWraGMdRz5BpfjMXEEQsn0tmgBbQNG0GUy3CSRXUS7QMMqqUKcY496KpBJm76-uWjTG9eGTRURKFoAypkdDXbyWborce0MffKddX-Fx_mevqlCEe0BYcIJo3NAFFcWcrs7cF64oc3Id3HvW2vX9338fJ5NpQM4H7m-TkIkww.CbRAimf8oo95_10AnYkOa5Z_SeyW0n1GsQFfL7PnBds"
COOKIE_VALUE   = "_sk_ni_108446=JtCq6KkU8aeYj5"          # the value after _sk_p2_155147 =

# ── Request Payload ───────────────────────────────────────────────────────────
payload = {
    "InstrumentId": "IRTKMOFD0001",
    "ISensOM": "Buy",          # "Buy" or "Sell"
    "YValiOmNSC": "Day",
    "DValiOM": None,
    "PLimSaiOM": 561000,       # Price
    "QTitTotOM": 2,          # Quantity
    "QTitDvlOM": 0,
    "ExecutionType": "Instant"
}

# ── Headers ───────────────────────────────────────────────────────────────────
headers = {
    "Authorization": AUTHORIZATION,
    "Cookie": COOKIE_VALUE,
    "Content-Type": "application/json"
}

# ── Call the Endpoint ─────────────────────────────────────────────────────────
url = f"{RED_ENDPOINT}/api/Orders/OrderEntry"

try:
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    data = response.json()
    print("✅ Success!")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # Quick access to highlighted fields
    if data.get("response", {}).get("successful"):
        order_data = data["response"]["data"]
        print(f"\n📌 Order ID     : {order_data.get('orderId')}")
        print(f"📌 Order Status : {order_data.get('orderStatus')}")
        print(f"📌 Order Side   : {order_data.get('orderSide')}")
        print(f"📌 Instrument   : {order_data.get('instrumentId')}")

except requests.exceptions.HTTPError as e:
    print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
except requests.exceptions.ConnectionError:
    print("❌ Connection Error: Could not reach the endpoint.")
except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {e}")
except json.JSONDecodeError:
    print(f"❌ Could not parse response as JSON:\n{response.text}")