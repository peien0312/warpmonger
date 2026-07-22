#!/usr/bin/env python3
"""Daily LINE nudges (VM crontab, 11:00): review requests + coupon expiry.

    venv/bin/python line_daily.py [--dry-run]

1. Review request: web order whose internal orders shipped 7–30 days ago,
   member LINE-bound, no review from them on any item yet -> one push
   (mentions the 評價禮 coupon when one is configured). Once per order.
2. Coupon expiry: granted, unused coupons expiring within 3 days -> one
   push per (member, code).

Push-quota guards (OA plan unknown): hard caps per run, one-shot markers
in memberdb.line_nudges, and every push lands in the POS chat log where
volume can be audited.
"""
import os
import sys
import sqlite3
from datetime import date, timedelta

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import memberdb   # noqa: E402
import posdb      # noqa: E402
import linepush   # noqa: E402

SITE = "https://abbeystoys.com"
MAX_REVIEW_PUSHES = 20
MAX_EXPIRY_PUSHES = 10
DRY = "--dry-run" in sys.argv


def _send(uid, text):
    if DRY:
        print(f"[dry] -> {uid[:12]}…: {text[:60]!r}")
        return True
    try:
        linepush.push_text(uid, text)
        return True
    except Exception as e:
        print(f"push failed ({uid[:12]}…): {e}")
        return False


def review_requests():
    if not linepush.enabled() and not DRY:
        return
    conn = posdb._conn()
    rows = [dict(r) for r in conn.execute("""
        SELECT wo.order_no, wo.phone, wo.email,
               MAX(o.shipped_date) AS shipped
        FROM web_orders wo JOIN orders o ON o.web_order_id = wo.id
        WHERE o.status IN ('已出貨', '已結帳')
          AND (o.is_deleted IS NULL OR o.is_deleted = 0)
          AND wo.status != '已取消'
        GROUP BY wo.id
        HAVING shipped <= datetime('now', '-7 days')
           AND shipped >= datetime('now', '-30 days')
        ORDER BY shipped DESC LIMIT 100
    """)]
    reward = None
    try:
        reward = posdb.get_auto_grant_coupon('review')
    except Exception:
        pass
    sent = 0
    for row in rows:
        if sent >= MAX_REVIEW_PUSHES:
            print("review push cap reached")
            break
        member = (memberdb.find_by_phone(row.get("phone"))
                  or memberdb.find_by_email(row.get("email")))
        if not member or not member.get("line_user_id"):
            continue
        order = posdb.get_web_order(row["order_no"])
        if not order or not order.get("items"):
            continue
        skus = [it.get("sku") for it in order["items"] if it.get("sku")]
        # skip if they already reviewed any item on the order
        mconn = sqlite3.connect(memberdb.DB_PATH)
        mconn.row_factory = sqlite3.Row
        ph = ",".join("?" * len(skus)) if skus else "''"
        reviewed = mconn.execute(
            f"SELECT 1 FROM product_reviews WHERE member_id = ? "
            f"AND sku IN ({ph}) LIMIT 1",
            [member["id"]] + skus).fetchone() if skus else None
        mconn.close()
        if reviewed:
            continue
        if not DRY and not memberdb.try_nudge("review", row["order_no"]):
            continue
        it = order["items"][0]
        name = it.get("zhtw_name") or it.get("en_name") or "商品"
        url = (f"{SITE}/products/{it.get('category_slug')}/{it.get('slug')}"
               if it.get("slug") else f"{SITE}/account")
        reward_txt = ""
        if reward and reward.get("code"):
            reward_txt = (f"\n留下評價即贈「{reward.get('title') or reward['code']}」"
                          f"折價券 🎁")
        if _send(member["line_user_id"],
                 f"感謝訂購「{name}」！商品都還喜歡嗎？\n"
                 f"歡迎到商品頁留下評價，讓其他玩家參考～{reward_txt}\n{url}"):
            sent += 1
    print(f"review requests: {sent} sent / {len(rows)} candidates")


def coupon_expiry():
    if not linepush.enabled() and not DRY:
        return
    today = date.today()
    horizon = (today + timedelta(days=3)).isoformat()
    coupons = {}
    try:
        for code in set(r["code"] for r in _granted_rows()):
            c = posdb.get_coupon(code)
            if not c or not c.get("valid_until"):
                continue
            vu = str(c["valid_until"])[:10]
            if today.isoformat() <= vu <= horizon:
                coupons[code] = (c, vu)
    except Exception as e:
        print(f"coupon expiry scan failed: {e}")
        return
    if not coupons:
        print("coupon expiry: nothing expiring")
        return
    sent = 0
    for row in _granted_rows():
        if sent >= MAX_EXPIRY_PUSHES:
            print("expiry push cap reached")
            break
        if row["code"] not in coupons:
            continue
        member = memberdb.member_by_id(row["member_id"]) if hasattr(
            memberdb, "member_by_id") else None
        if member is None:
            conn = sqlite3.connect(memberdb.DB_PATH)
            conn.row_factory = sqlite3.Row
            m = conn.execute("SELECT * FROM members WHERE id = ?",
                             (row["member_id"],)).fetchone()
            conn.close()
            member = dict(m) if m else None
        if not member or not member.get("line_user_id"):
            continue
        ref = f"{row['member_id']}:{row['code']}"
        if not DRY and not memberdb.try_nudge("coupon_exp", ref):
            continue
        c, vu = coupons[row["code"]]
        if _send(member["line_user_id"],
                 f"提醒您：優惠券「{c.get('title') or row['code']}」"
                 f"（折 NT${int(c.get('amount_twd') or 0)}）將於 {vu} 到期，"
                 f"別忘了使用！\n{SITE}/products"):
            sent += 1
    print(f"coupon expiry: {sent} sent")


def _granted_rows():
    conn = sqlite3.connect(memberdb.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute(
        "SELECT member_id, code FROM member_coupons WHERE status = 'granted'")]
    conn.close()
    return rows


if __name__ == "__main__":
    review_requests()
    coupon_expiry()
