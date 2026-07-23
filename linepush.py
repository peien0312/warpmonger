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
import urllib.error
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
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        # surface LINE's error detail (which field it rejected), not just 400
        try:
            detail = e.read().decode()[:300]
        except Exception:
            detail = ""
        raise RuntimeError(f"LINE API {e.code} {path}: {detail}") from None


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


def _quick_reply(chips):
    """chips: [{'label', 'text'}] (message action) or [{'label', 'data',
    'display'}] (postback action) -> LINE quickReply payload."""
    items = []
    for c in chips[:13]:
        if c.get("data"):
            action = {"type": "postback", "label": c["label"][:20],
                      "data": c["data"][:300],
                      "displayText": (c.get("display") or c["label"])[:300]}
        else:
            action = {"type": "message", "label": c["label"][:20],
                      "text": c.get("text") or c["label"]}
        items.append({"type": "action", "action": action})
    return {"items": items}


def push_text(line_user_id, text):
    r = _api("/v2/bot/message/push", {
        "to": line_user_id,
        "messages": [{"type": "text", "text": text[:4900]}],
    })
    log_to_pos({"line_user_id": line_user_id, "direction": "out",
                "msg_type": "text", "text": text[:4900]})
    return r


def push_flex(line_user_id, alt_text, bubbles, pretext=None):
    """One push call (= one quota unit) carrying an optional text line plus
    the flex carousel."""
    messages = []
    if pretext:
        messages.append({"type": "text", "text": pretext[:4900]})
    messages.append({"type": "flex", "altText": alt_text[:390],
                     "contents": {"type": "carousel",
                                  "contents": bubbles[:12]}})
    r = _api("/v2/bot/message/push", {
        "to": line_user_id, "messages": messages,
    })
    log_to_pos({"line_user_id": line_user_id, "direction": "out",
                "msg_type": "text",
                "text": ((pretext + "\n") if pretext else "") + alt_text[:390]})
    return r


def reply_text(reply_token, text, line_user_id=None, chips=None):
    msg = {"type": "text", "text": text[:4900]}
    if chips:
        msg["quickReply"] = _quick_reply(chips)
    r = _api("/v2/bot/message/reply", {
        "replyToken": reply_token, "messages": [msg],
    })
    if line_user_id:
        log_to_pos({"line_user_id": line_user_id, "direction": "out",
                    "msg_type": "text", "text": text[:4900]})
    return r


def reply_flex(reply_token, alt_text, bubbles, line_user_id=None, chips=None):
    """Reply with a Flex carousel (list of bubble dicts). alt_text shows in
    push previews and is what lands in the POS chat log."""
    msg = {"type": "flex", "altText": alt_text[:390],
           "contents": {"type": "carousel", "contents": bubbles[:12]}}
    if chips:
        msg["quickReply"] = _quick_reply(chips)
    r = _api("/v2/bot/message/reply", {
        "replyToken": reply_token, "messages": [msg],
    })
    if line_user_id:
        log_to_pos({"line_user_id": line_user_id, "direction": "out",
                    "msg_type": "text", "text": alt_text[:390]})
    return r


def valid_signature(body_bytes, signature):
    """Verify X-Line-Signature on a webhook request."""
    if not CHANNEL_SECRET or not signature:
        return False
    mac = hmac.new(CHANNEL_SECRET.encode(), body_bytes, hashlib.sha256)
    return hmac.compare_digest(base64.b64encode(mac.digest()).decode(), signature)


# ----- rich menu (圖文選單) -----
# Menus are created/replaced by setup_richmenu.py and resolved at runtime
# by name, so no IDs need storing: abbeys-guest (the default for everyone)
# and abbeys-member (linked per-user once they bind).

MENU_GUEST = "abbeys-guest"
MENU_MEMBER = "abbeys-member"

_menu_ids = {}  # name -> richMenuId, cached per process


def richmenu_list():
    with _get("https://api.line.me/v2/bot/richmenu/list") as resp:
        return json.loads(resp.read()).get("richmenus", [])


def richmenu_create(spec):
    """spec: size/selected/name/chatBarText/areas — returns richMenuId."""
    return _api("/v2/bot/richmenu", spec)["richMenuId"]


def richmenu_upload_image(rich_menu_id, png_bytes):
    req = urllib.request.Request(
        f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
        data=png_bytes,
        headers={"Content-Type": "image/png",
                 "Authorization": "Bearer " + ACCESS_TOKEN},
        method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def richmenu_delete(rich_menu_id):
    req = urllib.request.Request(
        f"https://api.line.me/v2/bot/richmenu/{rich_menu_id}",
        headers={"Authorization": "Bearer " + ACCESS_TOKEN},
        method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def richmenu_set_default(rich_menu_id):
    return _api(f"/v2/bot/user/all/richmenu/{rich_menu_id}", {})


def richmenu_id_by_name(name):
    """richMenuId for a menu created by setup_richmenu.py, or None."""
    if name not in _menu_ids:
        try:
            for m in richmenu_list():
                _menu_ids[m.get("name")] = m.get("richMenuId")
        except Exception as e:
            print(f"richmenu list failed: {e}")
            return None
    return _menu_ids.get(name)


def richmenu_link_user(line_user_id, name=MENU_MEMBER):
    """Best-effort: switch this user's menu (e.g. to the member menu on bind)."""
    rid = richmenu_id_by_name(name)
    if not rid:
        return False
    try:
        _api(f"/v2/bot/user/{line_user_id}/richmenu/{rid}", {})
        return True
    except Exception as e:
        print(f"richmenu link failed: {e}")
        return False
