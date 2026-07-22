"""LINE-login auto-merge: unseen LINE identities attach to the member bound
via 綁定碼 or matched by LINE-verified email, instead of forking accounts."""
import base64
import hashlib
import hmac
import json

import app as site
import memberdb


def _make_id_token(payload, secret=''):
    def enc(d):
        return base64.urlsafe_b64encode(
            json.dumps(d).encode()).rstrip(b'=').decode()
    head_body = f"{enc({'alg': 'HS256'})}.{enc(payload)}"
    sig = base64.urlsafe_b64encode(hmac.new(
        secret.encode(), head_body.encode(),
        hashlib.sha256).digest()).rstrip(b'=').decode()
    return f'{head_body}.{sig}'


def test_id_token_email_decode(app):
    tok = _make_id_token({'sub': 'U1', 'email': 'x@test.dev'},
                         secret=site.LINE_LOGIN_CHANNEL_SECRET)
    assert site._line_id_token_email(tok) == 'x@test.dev'
    bad = _make_id_token({'sub': 'U1', 'email': 'x@test.dev'},
                         secret=site.LINE_LOGIN_CHANNEL_SECRET + 'x')
    assert site._line_id_token_email(bad) is None  # bad signature
    assert site._line_id_token_email('garbage') is None


def test_merge_via_bind_code(app):
    """Google member bound via 綁定碼 -> later LINE login must land on the
    SAME member, not create a new one."""
    m = memberdb.find_or_create_by_identity(
        'google', 'merge-g-1', 'bound@test.dev', '綁定碼會員', None)
    memberdb.set_line_user(m['id'], 'Ubindcode1')

    got = site._resolve_line_member('Ubindcode1', None, 'LINE暱稱', None)
    assert got['id'] == m['id']
    assert got['_is_new'] is False
    assert memberdb.identities_for(m['id'])['line'] == 'Ubindcode1'


def test_merge_via_email(app):
    """Same LINE-verified email as an existing Google member -> attach."""
    m = memberdb.find_or_create_by_identity(
        'google', 'merge-g-2', 'same-mail@test.dev', 'Email會員', None)
    got = site._resolve_line_member(
        'Uemailmerge1', 'same-mail@test.dev', 'LINE暱稱', None)
    assert got['id'] == m['id']
    assert memberdb.identities_for(m['id'])['line'] == 'Uemailmerge1'


def test_no_match_creates_new(app):
    got = site._resolve_line_member('Ubrandnew1', 'nobody@test.dev', '新客', None)
    assert got['_is_new'] is True
    m2 = site._resolve_line_member('Ubrandnew1', None, '新客', None)
    assert m2['id'] == got['id'] and m2['_is_new'] is False


def test_ambiguous_email_not_merged(app):
    """Two members share an email -> refuse to guess, create a fresh one."""
    a = memberdb.find_or_create_by_identity(
        'google', 'dup-g-1', 'dup@test.dev', 'A', None)
    conn = memberdb._conn()
    conn.execute("INSERT INTO members (google_sub, email, name) "
                 "VALUES ('dup-g-2', 'dup@test.dev', 'B')")
    conn.commit()
    conn.close()
    got = site._resolve_line_member('Udupmail1', 'dup@test.dev', 'C', None)
    assert got['id'] != a['id']
    assert got['_is_new'] is True
