import requests
import json
from datetime import datetime

# ── Constants ─────────────────────────────────────────────────────────────────
RED_ENDPOINT   = "https://red.nibi.ir"
AUTHORIZATION  = "eyJhbGciOiJBMjU2R0NNS1ciLCJlbmMiOiJBMjU2Q0JDLUhTNTEyIiwiaXYiOiJtSmp3andjZlJuUGlkRTRwIiwidGFnIjoiWmNiYTBOeTNxOXRCRW9HUndKS1doUSJ9.yAqFCnSlW42ER7I0PWpt4aALq0NDraMil57i5WVCsX1Zw3Cbb0rvanQXJsqM2PJyT0cKHkR2LUq103RKNlgRuQ.ySOiBSvbOESksWYYNH-Dww.RU0usBsPk5L6MbyxLnm6LHTf2ye-SzpaCWlRxh3z2fJFpbcRMlSVR6Up-n6NXeu1QKpWv_-s7YaYEwEJtA7lPvRdcI3F9QlbfOrlpTSG5jZBtmfmiLyHxp4FUEEKOyV9X6a4-EPVk9qhW-_doV1UeWSNQUX99kZMN-7ZQyCR6CFNr0Uh7RHsp-3f4pilXI4kQ3sdTs1Ve-XnwTGQHiPRPahl3uUYI-J6Uht_9txedgNpAPnT9S7VgEYarO0pgYkWrfLMA4u_ksGtr9f5xMm7ZgiK3GEIN9_wBo7qawtEAQNHk50KnW9oPUKCMo3NKfdHCvNvz3yJ1G-5nwyu63c9lrXBJ9y7L9HIMauMZmST4Vk2_MuWDb96N4JXpQ9-YofFUWiu6DaVuxUKxz7MDvuxwAf_9X5clf_K1rH1cNZBTa4s-1R-Z_RvVefs-l7QGoWTOzRX_peaV4YvPGyoaHOE-UIlKoyCURtEFsdhxLx3dswju2fQ-s67F_0-0c_JOKQbYgS684v40rtDY88GXDGN1Roek9wJm2KwyyYUO8hpeI77oRlZhqh0JU5Ae3qLv7FkUHpw5SWdcVj3ik8Qz-L_9d0AlylOOO_m2JRkuC9MAZkoGUzdC_B8azJk2eGgxqMeRjbLCSRfGxDz6nkyia_EeyTLVRI1tI90RnlvgxaMmG_Z9xPd3fZBxExFNCUPKIfme66MslTLmmtoroDNzKbVfw.kxbQqRHcdCqUbSSK99GRiptEkBCD8kleWbFKAac19-E"
COOKIE_VALUE   = "cookiesession1=678A8C40F94139C3D358929C1FA000BD; _sk_ni_108446=7ev37vGPmYO0C"

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