"""LINE OA bot: search keyword parsing, Flex card building, text handling."""
import app as site


def test_parse_search_keyword():
    assert site._parse_search_keyword('找 暗源') == '暗源'
    assert site._parse_search_keyword('找暗源') == '暗源'
    assert site._parse_search_keyword('查 JT0001') == 'JT0001'
    assert site._parse_search_keyword('搜尋：劍聖') == '劍聖'
    assert site._parse_search_keyword('找') is None            # bare prefix
    assert site._parse_search_keyword('你好老闆') is None      # normal chat
    assert site._parse_search_keyword('') is None


def test_product_bubble_structure(app):
    products = site.get_products()
    assert products, 'fixture DB should have published products'
    p = products[0]
    b = site._product_bubble(p)
    assert b['type'] == 'bubble'
    uri = b['footer']['contents'][0]['action']['uri']
    assert uri == f"https://abbeystoys.com/products/{p['category']}/{p['slug']}"
    texts = [c['text'] for c in b['body']['contents']]
    assert any((p.get('zhtw_name') or p.get('title'))[:10] in t for t in texts)
    if p.get('images'):
        assert b['hero']['url'].startswith('https://')


def test_handle_line_text_search(app, monkeypatch):
    sent = {}

    def fake_flex(token, alt, bubbles, line_user_id=None, chips=None):
        sent['flex'] = (alt, bubbles)

    def fake_text(token, text, line_user_id=None, chips=None):
        sent['text'] = text

    import linepush
    monkeypatch.setattr(linepush, 'reply_flex', fake_flex)
    monkeypatch.setattr(linepush, 'reply_text', fake_text)

    products = site.get_products()
    kw = (products[0].get('zhtw_name') or products[0]['title'])[:3]
    assert site._handle_line_text('U1', f'找 {kw}', 'tok') is True
    assert 'flex' in sent
    alt, bubbles = sent['flex']
    assert kw in alt and 1 <= len(bubbles) <= 7

    sent.clear()
    assert site._handle_line_text('U1', '找 zzz不存在的東西zzz', 'tok') is True
    assert '找不到' in sent['text']

    sent.clear()
    assert site._handle_line_text('U1', '查 訂單', 'tok') is True
    assert '/line/entry' in sent['text']

    # ordinary chat -> bot stays silent (goes to the human/chat log)
    sent.clear()
    assert site._handle_line_text('U1', '老闆您好請問改造', 'tok') is False
    assert not sent


def test_search_mode_after_button(app, monkeypatch):
    sent = {}
    import linepush
    monkeypatch.setattr(linepush, 'reply_flex',
                        lambda tok, alt, b, line_user_id=None, chips=None: sent.__setitem__('flex', (alt, b)))
    monkeypatch.setattr(linepush, 'reply_text',
                        lambda tok, text, line_user_id=None, chips=None: sent.__setitem__('text', text))

    # 商品查詢 arms search mode -> next bare message is the keyword
    assert site._handle_line_text('U2', '商品查詢', 'tok') is True
    assert '輸入商品名稱' in sent['text']
    kw = (site.get_products()[0].get('zhtw_name') or site.get_products()[0]['title'])[:3]
    sent.clear()
    assert site._handle_line_text('U2', kw, 'tok') is True
    assert 'flex' in sent

    # mode is one-shot: same message again is plain chat now
    sent.clear()
    assert site._handle_line_text('U2', kw, 'tok') is False

    # a miss re-arms the mode so the next keyword still searches
    site._handle_line_text('U2', '商品查詢', 'tok')
    sent.clear()
    assert site._handle_line_text('U2', 'zzz沒有這個zzz', 'tok') is True
    assert '找不到' in sent['text']
    sent.clear()
    assert site._handle_line_text('U2', kw, 'tok') is True
    assert 'flex' in sent

    # long text while armed -> chat for the human, mode consumed
    site._handle_line_text('U2', '商品查詢', 'tok')
    sent.clear()
    assert site._handle_line_text(
        'U2', '老闆您好我想問上次那個改造的進度大概什麼時候好', 'tok') is False
    assert not sent


def _capture(monkeypatch):
    sent = {}
    import linepush
    monkeypatch.setattr(linepush, 'reply_flex',
                        lambda tok, alt, b, line_user_id=None, chips=None: sent.__setitem__('flex', (alt, b)))
    monkeypatch.setattr(linepush, 'reply_text',
                        lambda tok, text, line_user_id=None, chips=None: sent.__setitem__('text', text))
    return sent


def test_orders_and_coupons_need_binding(app, monkeypatch):
    sent = _capture(monkeypatch)
    assert site._handle_line_text('Unobody', '查訂單', 'tok') is True
    assert '綁定' in sent['text'] and '/line/entry' in sent['text']
    sent.clear()
    assert site._handle_line_text('Unobody', '我的優惠券', 'tok') is True
    assert '綁定' in sent['text']


def test_orders_carousel(app, monkeypatch):
    import memberdb
    m = memberdb.find_or_create_by_identity(
        'google', 'order-test-sub', 'member@test.dev', '訂單測試員', None)
    memberdb.set_line_user(m['id'], 'Uorders')
    conn = memberdb._conn()
    conn.execute("UPDATE members SET phone = ? WHERE id = ?",
                 ('0912345678', m['id']))
    conn.commit()
    conn.close()

    sent = _capture(monkeypatch)
    assert site._handle_line_text('Uorders', '查訂單', 'tok') is True
    alt, bubbles = sent['flex']
    assert '訂單查詢：2 筆' in alt
    # web order card + POS (LINE-chat) order card + trailing 會員中心 card
    assert len(bubbles) == 3
    all_text = str(bubbles)
    assert 'AB260722-001' in all_text
    assert '現貨測試品' in all_text           # item list inside the card
    assert 'NT$3,060' in all_text             # web: 1500*2 + 60 運費
    assert 'LINE 訂單' in all_text            # POS-direct order labeled by source
    assert '預購測試品' in all_text           # its item list
    assert 'NT$3,000' in all_text             # its total
    web_bubble = next(b for b in bubbles if 'AB260722-001' in str(b))
    uri = web_bubble['footer']['contents'][0]['action']['uri']
    assert '/order/AB260722-001?t=' in uri    # magic-link, no login needed
    assert '/line/entry' in str(bubbles[-1])  # auto-login account link


def test_line_entry_redirects_to_login(client):
    resp = client.get('/line/entry')
    assert resp.status_code == 302
    assert '/auth/line' in resp.headers['Location']
    assert 'account' in resp.headers['Location']


def test_coupons_carousel(app, monkeypatch):
    import memberdb
    m = memberdb.find_or_create_by_identity(
        'google', 'coupon-test-sub', 'coupon@test.dev', '優惠券測試員', None)
    memberdb.set_line_user(m['id'], 'Ucoupons')

    sent = _capture(monkeypatch)
    assert site._handle_line_text('Ucoupons', '我的優惠券', 'tok') is True
    assert '沒有可用的優惠券' in sent['text']

    memberdb.grant_coupon(m['id'], 'TESTC', 'manual', '')
    sent.clear()
    assert site._handle_line_text('Ucoupons', '我的優惠券', 'tok') is True
    alt, bubbles = sent['flex']
    assert '可用優惠券：1 張' in alt
    assert 'NT$50' in str(bubbles[0])
    assert '/line/entry' in str(bubbles[-1])


def test_new_arrivals_cards(app, monkeypatch):
    sent = {}
    import linepush
    monkeypatch.setattr(linepush, 'reply_flex',
                        lambda tok, alt, b, line_user_id=None, chips=None: sent.__setitem__('flex', (alt, b)))
    monkeypatch.setattr(linepush, 'reply_text',
                        lambda tok, text, line_user_id=None, chips=None: sent.__setitem__('text', text))
    assert site._handle_line_text('U3', '新品到貨', 'tok') is True
    # fixture products are freshly created -> all count as 新品
    assert 'flex' in sent
    alt, bubbles = sent['flex']
    assert '新品' in alt and bubbles


def test_richmenu_spec_areas():
    import setup_richmenu as rm
    for name, bar, cells, _f, _c in rm.MENUS:
        spec = rm.menu_spec(name, bar, cells)
        assert len(spec['areas']) == 6
        # areas must tile the full 2500x1686 canvas exactly
        assert sum(a['bounds']['width'] * a['bounds']['height']
                   for a in spec['areas']) == rm.W * rm.H
        for a in spec['areas']:
            assert a['action']['type'] in ('uri', 'message')


def test_wishlist_postback(app, monkeypatch):
    import memberdb
    m = memberdb.find_or_create_by_identity(
        'google', 'wish-test-sub', 'wish@test.dev', '收藏測試員', None)
    memberdb.set_line_user(m['id'], 'Uwish1')
    sent = _capture(monkeypatch)

    assert site._handle_line_postback('Uwish1', 'wish:JT0001', 'tok') is True
    assert '已加入收藏' in sent['text']
    assert 'JT0001' in memberdb.wishlist_skus(m['id'])

    sent.clear()
    assert site._handle_line_postback('Uwish1', 'wish:JT0001', 'tok') is True
    assert '移除' in sent['text']

    # unbound user -> bind prompt
    sent.clear()
    assert site._handle_line_postback('Unobody9', 'wish:JT0001', 'tok') is True
    assert '綁定' in sent['text']


def test_tagsearch_postback(app, monkeypatch):
    sent = _capture(monkeypatch)
    assert site._handle_line_postback('U1', 'tagsearch:ultramarines', 'tok') is True
    alt, bubbles = sent['flex']
    assert '極限戰士' in alt and bubbles


def test_search_chips_have_tags(app):
    chips = site._search_chips()
    labels = [c['label'] for c in chips]
    assert '極限戰士' in labels     # faction tag with zh glossary label
    assert '新品到貨' in labels


def test_narrowcast_segments(app):
    import memberdb
    import posdb
    m = memberdb.find_or_create_by_identity(
        'google', 'seg-test-sub', 'seg@test.dev', '分眾測試員', None)
    memberdb.set_line_user(m['id'], 'Useg1')
    memberdb.wishlist_toggle(m['id'], 'JT0002')
    assert 'Useg1' in memberdb.wishlist_line_user_ids(['JT0002'])
    # series buyers: fixture POS order is by 0912345678 (series unset -> empty ok)
    assert isinstance(posdb.series_buyer_phones(['JT0001']), list)


def test_showcase_page_renders(client):
    resp = client.get('/showcase')
    assert resp.status_code == 200
    assert '玩家分享'.encode() in resp.data
