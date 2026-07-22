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

    def fake_flex(token, alt, bubbles, line_user_id=None):
        sent['flex'] = (alt, bubbles)

    def fake_text(token, text, line_user_id=None):
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
    assert '/account' in sent['text']

    # ordinary chat -> bot stays silent (goes to the human/chat log)
    sent.clear()
    assert site._handle_line_text('U1', '老闆您好請問改造', 'tok') is False
    assert not sent


def test_search_mode_after_button(app, monkeypatch):
    sent = {}
    import linepush
    monkeypatch.setattr(linepush, 'reply_flex',
                        lambda tok, alt, b, line_user_id=None: sent.__setitem__('flex', (alt, b)))
    monkeypatch.setattr(linepush, 'reply_text',
                        lambda tok, text, line_user_id=None: sent.__setitem__('text', text))

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


def test_new_arrivals_cards(app, monkeypatch):
    sent = {}
    import linepush
    monkeypatch.setattr(linepush, 'reply_flex',
                        lambda tok, alt, b, line_user_id=None: sent.__setitem__('flex', (alt, b)))
    monkeypatch.setattr(linepush, 'reply_text',
                        lambda tok, text, line_user_id=None: sent.__setitem__('text', text))
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
