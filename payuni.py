"""PayUni (統一金流) integrated payment page (UPP).

Crypto matches PayUni's official PHP SDK exactly:
  EncryptInfo = hex( base64(ciphertext) + ":::" + base64(gcm_tag) )
    where ciphertext = AES-256-GCM(key=HashKey, iv=HashIV, http_build_query(info))
  HashInfo    = upper(sha256(HashKey + EncryptInfo + HashIV))

Env: PAYUNI_MER_ID, PAYUNI_HASH_KEY (32 chars), PAYUNI_HASH_IV (16 chars),
PAYUNI_SANDBOX (default 1 = sandbox).
"""
import os
import base64
import hashlib
from urllib.parse import urlencode, parse_qs

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

VERSION = "1.0"


def _key():
    return os.environ.get("PAYUNI_HASH_KEY", "").strip().encode()


def _iv():
    return os.environ.get("PAYUNI_HASH_IV", "").strip().encode()


def mer_id():
    return os.environ.get("PAYUNI_MER_ID", "").strip()


def enabled():
    return bool(mer_id() and _key() and _iv())


def api_url(route="upp"):
    sandbox = os.environ.get("PAYUNI_SANDBOX", "1") not in ("0", "false", "False", "")
    base = "https://sandbox-api.payuni.com.tw/api/" if sandbox else "https://api.payuni.com.tw/api/"
    return base + route


def encrypt(info: dict) -> str:
    data = urlencode(info).encode()
    enc = Cipher(algorithms.AES(_key()), modes.GCM(_iv())).encryptor()
    ct = enc.update(data) + enc.finalize()
    payload = base64.b64encode(ct) + b":::" + base64.b64encode(enc.tag)
    return payload.hex()


def decrypt(encrypt_str: str) -> dict:
    raw = bytes.fromhex(encrypt_str)
    ct_b64, tag_b64 = raw.split(b":::", 1)
    ct = base64.b64decode(ct_b64)
    tag = base64.b64decode(tag_b64)
    dec = Cipher(algorithms.AES(_key()), modes.GCM(_iv(), tag)).decryptor()
    data = (dec.update(ct) + dec.finalize()).decode()
    return {k: (v[0] if len(v) == 1 else v) for k, v in parse_qs(data).items()}


def hash_info(encrypt_str: str) -> str:
    return hashlib.sha256(_key() + encrypt_str.encode() + _iv()).hexdigest().upper()


def build_request(info: dict) -> dict:
    """Form fields to POST to the UPP endpoint (as an auto-submitting form)."""
    enc = encrypt(info)
    return {"MerID": mer_id(), "Version": VERSION,
            "EncryptInfo": enc, "HashInfo": hash_info(enc)}


def verify_callback(form) -> dict | None:
    """Validate a Notify/Return callback's HashInfo, return the decrypted
    trade info, or None if the signature doesn't match."""
    enc = (form.get("EncryptInfo") or "").strip()
    if not enc or (form.get("HashInfo") or "") != hash_info(enc):
        return None
    return decrypt(enc)


# instant-refund endpoint per PaymentType (credit/Apple/Google/Samsung = 1 via
# trade/close; wallets have their own). ATM(2)/CVS(3) need the offline flow.
_REFUND_ROUTE = {
    "6": "trade/common/refund/icash",     # 愛金卡
    "7": "trade/common/refund/aftee",     # AFTEE 先享後付
    "11": "trade/common/refund/jkopay",   # 街口
}


def refund(trade_no, amount, payment_type="1"):
    """Instant refund back to the payment source. PaymentType 1 (信用卡/
    Apple/Google/Samsung Pay) -> trade/close CloseType 2; 6/7/11 -> their
    endpoints. ATM(2)/CVS(3) can't be instant -> {needs_bank: True}.
    Returns {ok, needs_bank, status, message, result, raw}."""
    import time
    import json as _json
    import urllib.request
    import urllib.parse
    pt = str(payment_type or "1")
    if pt in ("2", "3"):
        return {"ok": False, "needs_bank": True, "status": "",
                "message": "非信用卡付款需退款轉匯", "result": {}, "raw": ""}
    route = _REFUND_ROUTE.get(pt, "trade/close")
    info = {"MerID": mer_id(), "TradeNo": str(trade_no),
            "TradeAmt": int(amount), "Timestamp": int(time.time())}
    if route == "trade/close":
        info["CloseType"] = 2
    req = build_request(info)
    data = urllib.parse.urlencode(req).encode()
    r = urllib.request.Request(
        api_url(route), data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "payuni"})
    raw = ""
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "needs_bank": False, "status": "ERROR",
                "message": str(e), "result": {}, "raw": f"request failed: {e}"}
    try:
        env = _json.loads(raw)
    except Exception:
        env = dict(urllib.parse.parse_qsl(raw))
    result = {}
    try:
        result = decrypt(env.get("EncryptInfo", "")) if env.get("EncryptInfo") else {}
    except Exception:
        pass
    status = str(env.get("Status", "")).upper()
    return {"ok": status == "SUCCESS", "needs_bank": False, "status": status,
            "message": result.get("Message") or env.get("Message", ""),
            "result": result, "raw": raw[:500]}


def offline_refund_fields(trade_no, base_url):
    """Build the offline_payment/refund hosted-page request for ATM/CVS refunds —
    the buyer enters their bank account on PayUni's page. Returns (url, fields)."""
    import time
    info = {"MerID": mer_id(), "TradeNo": str(trade_no), "Timestamp": int(time.time()),
            "ReturnURL": f"{base_url}/payuni/refund-done"}
    return api_url("offline_payment/refund"), build_request(info)
