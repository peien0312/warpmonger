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


def refund(trade_no, amount, close_type=2):
    """Refund a paid transaction via trade_close (CloseType 2 = 退款).
    Returns dict {ok, status, result, raw}. `trade_no` is PayUni's UNI序號."""
    import time
    import json as _json
    import urllib.request
    import urllib.parse
    info = {
        "MerID": mer_id(),
        "TradeNo": str(trade_no),
        "CloseType": close_type,     # 2 = 退款
        "TradeAmt": int(amount),
        "Timestamp": int(time.time()),
    }
    req = build_request(info)
    data = urllib.parse.urlencode(req).encode()
    r = urllib.request.Request(
        api_url("trade/close"), data=data, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    raw = ""
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "status": "ERROR", "result": {}, "raw": f"request failed: {e}"}
    try:
        env = _json.loads(raw)
    except Exception:
        env = dict(urllib.parse.parse_qsl(raw))
    enc = env.get("EncryptInfo", "")
    result = {}
    try:
        result = decrypt(enc) if enc else {}
    except Exception:
        pass
    status = str(env.get("Status", "")).upper()
    ok = status == "SUCCESS"
    return {"ok": ok, "status": status,
            "message": result.get("Message") or env.get("Message", ""),
            "result": result, "raw": raw[:500]}
