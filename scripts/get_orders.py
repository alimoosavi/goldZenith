import requests
import json
from datetime import datetime

# ── Constants ─────────────────────────────────────────────────────────────────
RED_ENDPOINT   = "https://red.nibi.ir"
AUTHORIZATION  = "eyJhbGciOiJBMjU2R0NNS1ciLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwiaXYiOiJUQmVsb19VYkt5a3d5SXk5IiwidGFnIjoiYkF0SlZqY1hlZWVORGZpbUtackM1ZyJ9.spcV3Qx_EMpVzRQoqUFtAxgIKKXes7NFkrCtgdEai5DF1UCUBNrK8i0oC37Jc00Jv_xN-6E4Lis0mdGoOhohUw.MFEjqBU8jgIt00kEcp7-1Q.hvqH7o0loJxtdiLFKo8aqdPz36Q1SGAHw4B0BzgpRWcNtui2RWgB_6F_qdt2VDWLGZTG6Jj30AqbhknZQXMAhHOPiH466kEeA7Co73nMPIoF6ubBlzI8WaWKU3VMfIus49Bj-iRAE3ySzgox7jdzyEjvUC5AjH-G06DjCnSCPcxNp5QrFewH3FMLj34llo4fNDvY6yQWVi4KA7KmqfiuYrXLOX37hL1kz_jN1aB-E9iPliK3KaGlyQRGdXxdGYZ-84YkiMdOmifhF0uCqu0vzDyEgWff5cpUINkIPPBnyZUB6oHN2x0E2yC5ZAXttaf_tByxz4unz5tdpFgdOofiiV2a9GeX5O67Aa1LX8yY5O2e5jtCmlKa4ar6E_Fk3MyUkzQLN-081346y_HK8aey76fg4sL6sAHGLliqXOuqgC1X9BWO5R-L579p3Nh_NMqUlolY2WN1DtTNV9ZS0OXYjzz2t8TBT6C-oYibNWnKw8Av9_63o5Y4KtHdckRafoQq8fBSnJjG1EwGLr_9AEfZXb4WbED53mbO5LDSf_ye_uFM3Xu-d8xXIbduUzbdw0iKLRYFp_RM5mAS4Iux2i7_I7R13FTcF7u7lnLLmWY3HIhYfCNHt9oKfJSzMv-Q6hGriEdy4YrWxO86JT4M3LD24HbMbF9ivo5aj2P9uS8uMGYFyU9cDFFSY2ZklGg3kWazBHbOWxpd5_m2Uq__bmE55w.pC32itGceWx7t-J1X4mFbt6_xA9JKORiqBNuUS-kPBY"
COOKIE_VALUE   = "_sk_ni_108446=A1fN2S1xQLudTy"

# ── History Date ──────────────────────────────────────────────────────────────
HISTORY_DATE = datetime.now().strftime("%Y%m%d")   # defaults to today
# HISTORY_DATE = "20250226"                        # or set a fixed date manually

# ── Headers ───────────────────────────────────────────────────────────────────
headers = {
    "Authorization": AUTHORIZATION,
    "Cookie": COOKIE_VALUE,
    "Content-Type": "application/json"
}

# ── Call the Endpoint ─────────────────────────────────────────────────────────
url = f"{RED_ENDPOINT}/api/Orders/GetOrders?historyDate={HISTORY_DATE}"

try:
    response = requests.get(url, headers=headers)   # ← changed to GET
    response.raise_for_status()

    data = response.json()
    print(f"✅ Got order history for date: {HISTORY_DATE}")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # Summary
    resp = data.get("response", {})
    if resp.get("successful"):
        orders = resp.get("data", [])
        print(f"\n📋 Total orders returned: {len(orders)}")
        for i, order in enumerate(orders, 1):
            print(f"\n  Order #{i}")
            print(f"    Order ID     : {order.get('orderId')}")
            print(f"    Instrument   : {order.get('instrumentId')}")
            print(f"    Side         : {order.get('orderSide')}")
            print(f"    Status       : {order.get('orderStatus')}")
            print(f"    Price        : {order.get('price')}")
            print(f"    Quantity     : {order.get('quantity')}")
    else:
        print("\n❌ Request was not successful.")
        if resp.get("errors"):
            print(f"   Errors: {resp['errors']}")

except requests.exceptions.HTTPError as e:
    print(f"❌ HTTP Error: {e.response.status_code} - {e.response.text}")
except requests.exceptions.ConnectionError:
    print("❌ Connection Error: Could not reach the endpoint.")
except requests.exceptions.RequestException as e:
    print(f"❌ Request failed: {e}")
except json.JSONDecodeError:
    print(f"❌ Could not parse response as JSON:\n{response.text}")