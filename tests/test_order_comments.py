"""訂單留言 on /account: thread render + posting authorization.

The actual comment write goes through the POS storefront API (not running
in this harness), so POST success paths aren't covered here — the POS repo
tests those. Here: the account page renders the thread from the POS DB,
and the site-side authorization gates hold.
"""
import os
import sqlite3

import memberdb


def _login(client, member_id):
    with client.session_transaction() as sess:
        sess['member_id'] = member_id


def _member_matching_fixture_order():
    m = memberdb.find_or_create_by_identity(
        'google', 'comment-tester', 'member@test.dev', '留言測試', None)
    memberdb.set_member_phone(m['id'], '0912345678')
    return m


def _add_pos_comment(**cols):
    conn = sqlite3.connect(os.environ['POS_DB'])
    conn.execute(
        "INSERT INTO order_comments (web_order_id, inquiry_id, author, body) "
        "VALUES (?, ?, ?, ?)",
        (cols.get('web_order_id'), cols.get('inquiry_id'),
         cols['author'], cols['body']))
    conn.commit()
    conn.close()


def test_account_renders_comment_thread(client):
    m = _member_matching_fixture_order()
    conn = sqlite3.connect(os.environ['POS_DB'])
    wo_id = conn.execute(
        "SELECT id FROM web_orders WHERE order_no = 'AB260722-001'"
    ).fetchone()[0]
    conn.close()
    _add_pos_comment(web_order_id=wo_id, author='customer', body='改成紅色頭盔')
    _add_pos_comment(web_order_id=wo_id, author='shop', body='收到，加一百')

    _login(client, m['id'])
    page = client.get('/account')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert '訂單留言' in html
    assert '改成紅色頭盔' in html
    assert '收到，加一百' in html
    assert '留言送出後無法修改' in html


def test_converted_order_card_shows_inquiry_thread(client):
    """A quote-accepted internal order (其他訂單) shares its source
    inquiry's thread — the same log renders on the order card too."""
    m = _member_matching_fixture_order()
    conn = sqlite3.connect(os.environ['POS_DB'])
    order_id, cust_id = conn.execute(
        "SELECT id, customer_id FROM orders WHERE source = 'line' LIMIT 1"
    ).fetchone()
    cur = conn.execute(
        "INSERT INTO inquiries (customer_id, order_id, status) "
        "VALUES (?, ?, '已確認')", (cust_id, order_id))
    inq_id = cur.lastrowid
    conn.commit()
    conn.close()
    _add_pos_comment(inquiry_id=inq_id, author='customer', body='桂冠改金色')

    _login(client, m['id'])
    html = client.get('/account').get_data(as_text=True)
    assert '其他訂單' in html
    assert '網站上線前' not in html
    assert '桂冠改金色' in html


def test_comment_post_requires_auth(client):
    # anonymous, no token -> not authorized for the order
    r = client.post('/api/account/order-comment',
                    json={'order_no': 'AB260722-001', 'body': 'hi'})
    assert r.status_code == 403

    # empty body rejected before any auth work
    r = client.post('/api/account/order-comment',
                    json={'order_no': 'AB260722-001', 'body': '  '})
    assert r.status_code == 400

    # inquiry anchor needs a login
    r = client.post('/api/account/order-comment',
                    json={'inquiry_id': 1, 'body': 'hi'})
    assert r.status_code == 403


def test_comment_post_rejects_foreign_inquiry(client):
    m = memberdb.find_or_create_by_identity(
        'google', 'other-member', 'other@test.dev', '別人', None)
    _login(client, m['id'])
    r = client.post('/api/account/order-comment',
                    json={'inquiry_id': 99999, 'body': 'hi'})
    assert r.status_code == 403
