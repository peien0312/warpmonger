"""LINE Messaging API client — push through the 阿北玩具堂 官方帳號.

Env:
  LINE_CHANNEL_ACCESS_TOKEN  (long-lived, Messaging API channel)
  LINE_CHANNEL_SECRET        (same channel; used to verify webhook signatures)
"""
import base64
import hashlib
import hmac
import json
import os
import urllib.request

ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")


def enabled():
    return bool(ACCESS_TOKEN and CHANNEL_SECRET)


def _api(path, body):
    req = urllib.request.Request(
        "https://api.line.me" + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + ACCESS_TOKEN},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def push_text(line_user_id, text):
    return _api("/v2/bot/message/push", {
        "to": line_user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    })


def reply_text(reply_token, text):
    return _api("/v2/bot/message/reply", {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    })


def valid_signature(body_bytes, signature):
    """Verify X-Line-Signature on a webhook request."""
    if not CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode(), body_bytes, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), signature)
