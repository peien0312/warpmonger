"""Transactional email — branded HTML with a plain-text fallback.

Centralizes SMTP sending (previously inlined in app.py). Renders Jinja
templates under templates/emails/. Runs inside a Flask request context, so
render_template resolves against the app's template loader.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from email.header import Header

from flask import render_template

DELIVERY_LABEL = {"711": "7-11", "fami": "全家", "post": "郵局宅配", "meet": "面交"}
PAYMENT_LABEL = {"cod": "取貨付款", "transfer": "銀行轉帳", "linepay": "LINE Pay"}
AVAIL_LABEL = {"in_stock": "現貨", "incoming": "約2週到貨", "preorder": "預購",
               "orderable": "可訂購", "inquiry": "詢價"}
NOW_STATES = ("in_stock", "incoming", "orderable")

SENDER_NAME = "阿北玩具堂"


def _site_url():
    return os.environ.get("SITE_URL", "https://abbeystoys.com").rstrip("/")


def _smtp_conf():
    host = os.environ.get("SMTP_SERVER")
    user = os.environ.get("SMTP_USERNAME")
    pw = os.environ.get("SMTP_PASSWORD")
    if not all([host, user, pw]):
        return None
    sender = os.environ.get("SMTP_FROM", user)
    return {
        "host": host, "port": int(os.environ.get("SMTP_PORT", 587)),
        "user": user, "pw": pw, "from": sender,
        "reply_to": os.environ.get("REPLY_TO", sender),
    }


def send_email(to, subject, html, text):
    """Send one multipart/alternative email to each target. `to` is a str or
    an iterable of addresses. Best-effort: returns True if anything was sent."""
    conf = _smtp_conf()
    if not conf:
        return False
    targets = [to] if isinstance(to, str) else list(to)
    targets = [t for t in dict.fromkeys(t for t in targets if t)]  # dedupe, drop blanks
    if not targets:
        return False
    from_hdr = formataddr((str(Header(SENDER_NAME, "utf-8")), conf["from"]))
    sent = False
    try:
        with smtplib.SMTP(conf["host"], conf["port"]) as server:
            server.starttls()
            server.login(conf["user"], conf["pw"])
            for t in targets:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = from_hdr
                msg["To"] = t
                msg["Reply-To"] = conf["reply_to"]
                msg.attach(MIMEText(text, "plain", "utf-8"))
                msg.attach(MIMEText(html, "html", "utf-8"))
                server.sendmail(conf["from"], t, msg.as_string())
                sent = True
    except Exception as e:
        print(f"send_email failed: {e}")
    return sent


def _order_ctx(order_no, data, lines, totals, bank_info, order_url=None):
    items, has_pre, has_now, has_inq = [], False, False, False
    for l in lines:
        av = l.get("availability")
        if av == "preorder":
            has_pre = True
        elif av in NOW_STATES:
            has_now = True
        if av == "inquiry":
            has_inq = True
        items.append({
            "title": l.get("title"), "qty": l.get("qty"),
            "price": l.get("price") or 0, "avail_label": AVAIL_LABEL.get(av, av or ""),
            "line_total": (l.get("price") or 0) * l.get("qty", 1),
        })
    pm = data.get("payment_method")
    delivery = data.get("delivery_method")
    return {
        "order_no": order_no,
        "name": data.get("name"), "phone": data.get("phone"),
        "recipient_name": data.get("recipient_name") or data.get("name"),
        "recipient_phone": data.get("recipient_phone") or data.get("phone"),
        "delivery_label": DELIVERY_LABEL.get(delivery, delivery or ""),
        "dest": data.get("store_name") or data.get("address") or "",
        "payment_method": pm, "payment_label": PAYMENT_LABEL.get(pm, pm or ""),
        "ship_together": bool(data.get("ship_together", True)),
        "items": items,
        "subtotal": int(totals.get("total_twd", 0) or 0),
        "shipping_fee": int(totals.get("shipping_fee_twd", 0) or 0),
        "grand_total": int(totals.get("grand_total_twd", 0) or 0),
        "charge_now": int(totals.get("charge_now_twd",
                                     totals.get("grand_total_twd", 0)) or 0),
        "has_preorder": has_pre, "has_now": has_now, "has_inquiry": has_inq,
        "note": data.get("note"),
        "bank_info": bank_info,
        "order_url": order_url,
        "site_url": _site_url(),
    }


def send_order_confirmation(order_no, data, lines, totals, bank_info,
                            shop_email=None, order_url=None):
    """Order-received email to the customer (and a copy to the shop)."""
    ctx = _order_ctx(order_no, data, lines, totals, bank_info, order_url=order_url)
    html = render_template("emails/order_confirmation.html", **ctx)
    text = render_template("emails/order_confirmation.txt", **ctx)
    subject = f"[阿北玩具堂] 訂單確認 {order_no}"
    targets = []
    if shop_email:
        targets.append(shop_email)
    if data.get("email"):
        targets.append(data["email"])
    return send_email(targets, subject, html, text)


def render_status_html(headline, paragraphs, bank_info=None, order_no=None):
    """Branded HTML for a status-update / notification email."""
    return render_template(
        "emails/order_status.html", headline=headline, paragraphs=paragraphs,
        bank_info=bank_info, order_no=order_no, site_url=_site_url())


def render_status_text(headline, paragraphs, bank_info=None):
    return render_template(
        "emails/order_status.txt", headline=headline, paragraphs=paragraphs,
        bank_info=bank_info)


def render_quote_html(inquiry_no, items, expires_at):
    return render_template("emails/quote.html", inquiry_no=inquiry_no,
                           items=items, expires_at=expires_at, site_url=_site_url())


def render_quote_text(inquiry_no, items, expires_at):
    return render_template("emails/quote.txt", inquiry_no=inquiry_no,
                           items=items, expires_at=expires_at, site_url=_site_url())
