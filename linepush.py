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

# Chat-log mirror: every message (in via webhook, out via push) is
# best-effort POSTed to the POS, which stores it (LINE 訊息 page there).
POS_API_URL = os.environ.get("POS_API_URL", "http://127.0.0.1:8000")
STOREFRONT_API_KEY = os.environ.get("STOREFRONT_API_KEY", "")


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


def _get(url):
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + ACCESS_TOKEN})
    return urllib.request.urlopen(req, timeout=15)


def get_profile(line_user_id):
    """{displayName, pictureUrl, ...} or {} on any failure."""
    try:
        with _get(f"https://api.line.me/v2/bot/profile/{line_user_id}") as resp:
            return json.loads(resp.read())
    except Exception:
        return {}


def get_content(message_id):
    """(bytes, content_type) of an image/media message's payload."""
    with _get(f"https://api-data.line.me/v2/bot/message/{message_id}/content") as resp:
        return resp.read(), resp.headers.get("Content-Type", "image/jpeg")


def log_to_pos(payload):
    """Best-effort mirror of one message into the POS chat log."""
    if not STOREFRONT_API_KEY:
        return
    try:
        req = urllib.request.Request(
            POS_API_URL + "/api/storefront/line-messages",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "X-Storefront-Key": STOREFRONT_API_KEY},
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"line log_to_pos failed: {e}")


def push_text(line_user_id, text):
    r = _api("/v2/bot/message/push", {
        "to": line_user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    })
    log_to_pos({"line_user_id": line_user_id, "direction": "out",
                "msg_type": "text", "text": text[:4900]})
    return r


def reply_text(reply_token, text, line_user_id=None):
    r = _api("/v2/bot/message/reply", {
        "replyToken": reply_token,
        "messages": [{"type": "text", "text": text[:4900]}],
    })
    if line_user_id:
        log_to_pos({"line_user_id": line_user_id, "direction": "out",
                    "msg_type": "text", "text": text[:4900]})
    return r


def valid_signature(body_bytes, signature):
    """Verify X-Line-Signature on a webhook request."""
    if not CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode(), body_bytes, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), signature)
