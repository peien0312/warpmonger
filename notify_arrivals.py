#!/usr/bin/env python3
"""Daily job: email members whose 到貨通知 products are now in stock.

Run from the site directory (cron on the VM):
    venv/bin/python notify_arrivals.py
"""
import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import memberdb   # noqa: E402
import posdb      # noqa: E402

SITE = "https://abbeystoys.com"


def main():
    pending = memberdb.pending_notifications()
    if not pending:
        print("no pending notifications")
        return

    by_sku = {p["id"]: p for p in posdb.get_products()}

    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_user = os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    if not all([smtp_server, smtp_user, smtp_pass]):
        print("SMTP not configured; skipping")
        return

    sent = 0
    with smtplib.SMTP(smtp_server, int(os.environ.get("SMTP_PORT", 587))) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        for req_id, email, name, sku in pending:
            product = by_sku.get(sku)
            if not product or product["availability"] != "in_stock":
                continue
            url = f"{SITE}/products/{product['category']}/{product['slug']}"
            title = product["zhtw_name"] or product["title"]
            body = (f"{name or ''} 您好，\n\n"
                    f"您訂閱的商品「{title}」已到貨！\n\n{url}\n\n"
                    f"數量有限，欲購從速。\n— ABBEY'S TOYS 阿北玩具堂")
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = f"[阿北玩具堂] 到貨通知：{title}"
            msg["From"] = smtp_user
            msg["To"] = email
            try:
                server.sendmail(smtp_user, email, msg.as_string())
                memberdb.mark_notified(req_id)
                sent += 1
            except Exception as e:
                print(f"send to {email} failed: {e}")
    print(f"sent {sent} notifications")


if __name__ == "__main__":
    main()
