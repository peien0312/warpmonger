"""LINE Pay Online API v3 client (request -> redirect -> confirm).

Configured via env:
  LINEPAY_CHANNEL_ID / LINEPAY_CHANNEL_SECRET  (from LINE Pay 商家中心)
  LINEPAY_API_BASE   default sandbox: https://sandbox-api-pay.line.me
                     production:      https://api-pay.line.me
Enabled only when both channel envs are present.
"""
import base64
import hashlib
import hmac
import json
import os
import uuid
import urllib.request
import urllib.error

CHANNEL_ID = os.environ.get("LINEPAY_CHANNEL_ID", "")
CHANNEL_SECRET = os.environ.get("LINEPAY_CHANNEL_SECRET", "")
API_BASE = os.environ.get("LINEPAY_API_BASE", "https://sandbox-api-pay.line.me")


def enabled():
    return bool(CHANNEL_ID and CHANNEL_SECRET)


def _call(uri, body):
    """Signed POST to the LINE Pay API. Returns the parsed JSON response."""
    payload = json.dumps(body)
    nonce = str(uuid.uuid4())
    mac = hmac.new(
        CHANNEL_SECRET.encode(),
        (CHANNEL_SECRET + uri + payload + nonce).encode(),
        hashlib.sha256,
    )
    req = urllib.request.Request(
        API_BASE + uri, data=payload.encode(),
        headers={
            "Content-Type": "application/json",
            "X-LINE-ChannelId": CHANNEL_ID,
            "X-LINE-Authorization-Nonce": nonce,
            "X-LINE-Authorization": base64.b64encode(mac.digest()).decode(),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def request_payment(order_no, amount, product_name, confirm_url, cancel_url):
    """Create a payment request. Returns (payment_url, transaction_id) or
    raises RuntimeError with the LINE Pay error message."""
    amount = int(round(amount))
    result = _call("/v3/payments/request", {
        "amount": amount,
        "currency": "TWD",
        "orderId": order_no,
        "packages": [{
            "id": order_no,
            "amount": amount,
            "name": "ABBEY'S TOYS 阿北玩具堂",
            "products": [{
                "name": product_name[:250],
                "quantity": 1,
                "price": amount,
            }],
        }],
        "redirectUrls": {
            "confirmUrl": confirm_url,
            "cancelUrl": cancel_url,
            "confirmUrlType": "CLIENT",
        },
    })
    if result.get("returnCode") != "0000":
        raise RuntimeError(f"LINE Pay request failed: "
                           f"{result.get('returnCode')} {result.get('returnMessage')}")
    info = result["info"]
    return info["paymentUrl"]["web"], info["transactionId"]


def confirm_payment(transaction_id, amount):
    """Confirm an approved payment. Returns True on success."""
    result = _call(f"/v3/payments/{transaction_id}/confirm", {
        "amount": int(round(amount)),
        "currency": "TWD",
    })
    if result.get("returnCode") != "0000":
        raise RuntimeError(f"LINE Pay confirm failed: "
                           f"{result.get('returnCode')} {result.get('returnMessage')}")
    return True
