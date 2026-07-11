#!/usr/bin/env python3
"""Daily job (10:00 VM crontab): notify members when products they're waiting
on are back in stock — both explicit 到貨通知 subscriptions and wishlist items.

Run from the site directory:
    venv/bin/python notify_arrivals.py
    venv/bin/python notify_arrivals.py --dry-run   # print, no sends/writes

Phases:
  0. Re-arm wishlist rows whose product is no longer in stock (so the next
     restock notifies again). One-run-a-day cadence makes flap-guards moot.
  1. 到貨通知 subscriptions (notify_requests): unchanged copy. Successful sends
     collect (member_id, sku) into `handled`.
  2. Wishlist restocks: skip products not in stock; if the member already got
     a 到貨通知 for this SKU today, mark the wishlist row silently (no echo
     tomorrow) instead of sending a second message.
"""
import os
import sys
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import memberdb   # noqa: E402
import posdb      # noqa: E402
import linepush   # noqa: E402

SITE = "https://abbeystoys.com"


def _channel(email, line_user_id):
    """Which delivery channel would be used: 'line' (preferred when bound and
    push is enabled), else 'email' when an address is on file, else None."""
    if line_user_id and linepush.enabled():
        return "line"
    if email:
        return "email"
    return None


def _send(email, line_user_id, subject, body, smtp_ctx):
    """Deliver one notification, LINE-first with email fallback. Reuses the
    lazily-opened SMTP connection stored in smtp_ctx. Returns True on delivery.
    """
    if line_user_id and linepush.enabled():
        try:
            linepush.push_text(line_user_id, body)
            return True
        except Exception as e:
            print(f"line push to member failed: {e}")
    if not (smtp_ctx["ok"] and email):
        return False
    try:
        if smtp_ctx["server"] is None:
            server = smtplib.SMTP(smtp_ctx["host"], smtp_ctx["port"])
            server.starttls()
            server.login(smtp_ctx["user"], smtp_ctx["pass"])
            smtp_ctx["server"] = server
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_ctx["from"]
        msg["To"] = email
        msg["Reply-To"] = smtp_ctx["reply_to"]
        smtp_ctx["server"].sendmail(smtp_ctx["from"], email, msg.as_string())
        return True
    except Exception as e:
        print(f"send to {email} failed: {e}")
        return False


def _dry_line(channel, member_id, email, sku, subject):
    target = f"member {member_id}" if channel == "line" else email
    return f"[dry] {channel.upper()}→{target} sku={sku}: {subject}"


def main(dry_run=False):
    smtp_from = os.environ.get("SMTP_FROM", os.environ.get("SMTP_USERNAME"))
    smtp_ctx = {
        "host": os.environ.get("SMTP_SERVER"),
        "port": int(os.environ.get("SMTP_PORT", 587)),
        "user": os.environ.get("SMTP_USERNAME"),
        "pass": os.environ.get("SMTP_PASSWORD"),
        "from": smtp_from,
        "reply_to": os.environ.get("REPLY_TO", smtp_from),
        "server": None,
    }
    smtp_ctx["ok"] = all([smtp_ctx["host"], smtp_ctx["user"], smtp_ctx["pass"]])

    by_sku = {p["id"]: p for p in posdb.get_products()}

    def _in_stock(sku):
        p = by_sku.get(sku)
        return p if (p and p["availability"] == "in_stock") else None

    # ----- Phase 0: re-arm wishlist rows no longer in stock -----
    rearm = [row_id for row_id, sku in memberdb.notified_wishlist_rows()
             if not _in_stock(sku)]
    if dry_run:
        print(f"[dry] re-arm {len(rearm)} rows")
    else:
        memberdb.rearm_wishlist_rows(rearm)

    # ----- Phase 1: 到貨通知 subscriptions -----
    handled = set()
    sent = 0
    for req_id, member_id, email, name, sku, line_user_id in memberdb.pending_notifications():
        product = _in_stock(sku)
        if not product:
            continue
        url = f"{SITE}/products/{product['category']}/{product['slug']}"
        title = product["zhtw_name"] or product["title"]
        subject = f"[阿北玩具堂] 到貨通知：{title}"
        body = (f"{name or ''} 您好，\n\n"
                f"您訂閱的商品「{title}」已到貨！\n\n{url}\n\n"
                f"數量有限，欲購從速。\n— ABBEY'S TOYS 阿北玩具堂")
        if dry_run:
            channel = _channel(email, line_user_id)
            if channel is None:
                continue
            print(_dry_line(channel, member_id, email, sku, subject))
            handled.add((member_id, sku))
            sent += 1
            continue
        if _send(email, line_user_id, subject, body, smtp_ctx):
            memberdb.mark_notified(req_id)
            handled.add((member_id, sku))
            sent += 1

    # ----- Phase 2: wishlist restocks -----
    wl_sent = 0
    wl_suppressed = 0
    for row_id, member_id, email, name, sku, line_user_id in memberdb.pending_wishlist_restocks():
        product = _in_stock(sku)
        if not product:
            continue
        if (member_id, sku) in handled:
            # already told via 到貨通知 today — mark so we don't echo tomorrow
            if dry_run:
                print(f"[dry] mark wishlist row {row_id} sku={sku} "
                      f"(suppressed, dup of 到貨通知)")
            else:
                memberdb.mark_wishlist_notified(row_id)
            wl_suppressed += 1
            continue
        url = f"{SITE}/products/{product['category']}/{product['slug']}"
        title = product["zhtw_name"] or product["title"]
        subject = f"[阿北玩具堂] 收藏商品到貨：{title}"
        body = (f"{name or ''} 您好，\n\n"
                f"你收藏的商品「{title}」現在有現貨了！\n\n{url}\n\n"
                f"數量有限，欲購從速。\n— ABBEY'S TOYS 阿北玩具堂")
        if dry_run:
            channel = _channel(email, line_user_id)
            if channel is None:
                continue
            print(_dry_line(channel, member_id, email, sku, subject))
            wl_sent += 1
            continue
        if _send(email, line_user_id, subject, body, smtp_ctx):
            memberdb.mark_wishlist_notified(row_id)
            wl_sent += 1

    if smtp_ctx["server"] is not None:
        smtp_ctx["server"].quit()

    prefix = "[dry] " if dry_run else ""
    print(f"{prefix}phase0 re-armed {len(rearm)} rows")
    print(f"{prefix}phase1 到貨通知 sent {sent}")
    print(f"{prefix}phase2 wishlist sent {wl_sent}, suppressed {wl_suppressed}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
