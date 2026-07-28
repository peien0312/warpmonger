"""荷魯斯滾球 skeeball API: beta gate, wallet, session anti-cheat, prize grant."""
import os
import sqlite3

import memberdb
import skeeball


def _login(client, member_id):
    with client.session_transaction() as sess:
        sess['member_id'] = member_id


def _member(suffix='player'):
    m = memberdb.find_or_create_by_identity(
        'google', f'skeeball-{suffix}', f'{suffix}@test.dev', '滾球玩家', None)
    return m


def _seed_prizes():
    conn = sqlite3.connect(os.environ['POS_DB'])
    for code, title, amt in (
            ('SKEE-S', '滾球小獎 NT$30', 30),
            ('SKEE-L', '滾球大獎 NT$100', 100),
            ('SKEE-GOLD', '金色頂孔頭獎 NT$300', 300)):
        conn.execute(
            "INSERT OR IGNORE INTO coupons "
            "(code, title, kind, amount_twd, min_spend_twd, per_member_limit, "
            " auto_grant, active) VALUES (?, ?, 'fixed', ?, 0, 99, 'skeeball', 1)",
            (code, title, amt))
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES ('skeeball_prizes', ?)",
        ('{"tiers": [{"min_score": 1, "code": "SKEE-S"},'
         ' {"min_score": 300, "code": "SKEE-L"}],'
         ' "apex_code": "SKEE-GOLD"}',))
    conn.commit()
    conn.close()
    import posdb
    posdb._cache.clear()   # mtime-based cache; force-drop for same-ms writes


def _play_full_game(client, scores):
    start = client.post('/api/skeeball/session/start').get_json()
    sid, nonce = start['sessionId'], start['nonce']
    for i, score in enumerate(scores, start=1):
        r = client.post(f'/api/skeeball/session/{sid}/roll', json={
            'rollIndex': i, 'pinsHit': 1 if score else 0, 'score': score,
            'nonce': nonce, 'clientTs': 1})
        assert r.status_code == 200, r.get_json()
    return client.post(f'/api/skeeball/session/{sid}/complete').get_json()


def test_beta_gate_and_game_page(client, monkeypatch):
    m = _member('gate')
    monkeypatch.delenv('SKEEBALL_BETA_MEMBERS', raising=False)
    _login(client, m['id'])
    assert client.get('/game').status_code == 404          # beta off
    assert client.get('/api/skeeball/user/balance').status_code == 401

    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', str(m['id']))
    assert client.get('/api/skeeball/user/balance').status_code == 200

    other = _member('other')
    _login(client, other['id'])
    assert client.get('/game').status_code == 404          # not on the list
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    assert client.get('/api/skeeball/user/balance').status_code == 200

    with client.session_transaction() as sess:
        sess.clear()
    assert client.get('/game').status_code == 302          # anon → login


def test_tokens_spend_and_402(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    m = _member('tokens')
    _login(client, m['id'])
    assert client.post('/api/skeeball/session/start').status_code == 402

    assert memberdb.skeeball_grant_tokens(m['id'], 2, 'test') == 2
    assert client.post('/api/skeeball/session/start').status_code == 201
    bal = client.get('/api/skeeball/user/balance').get_json()
    assert bal['tokenBalance'] == 1
    # negative grants clamp at zero
    assert memberdb.skeeball_grant_tokens(m['id'], -5, 'revoke') == 0


def test_full_game_grants_tier_prize(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    monkeypatch.setattr(skeeball, 'MIN_MS_BETWEEN_ROLLS', 0)
    _seed_prizes()
    m = _member('winner')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')

    result = _play_full_game(client, [100, 150, 50])
    assert result['totalScore'] == 300
    assert result['golden'] is False
    assert result['prize']['title'] == '滾球大獎 NT$100'
    wallet = memberdb.list_coupons(m['id'])
    assert any(r['code'] == 'SKEE-L' and r['source'] == 'skeeball'
               for r in wallet)


def test_apex_hit_wins_jackpot(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    monkeypatch.setattr(skeeball, 'MIN_MS_BETWEEN_ROLLS', 0)
    _seed_prizes()
    m = _member('golden')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')

    result = _play_full_game(client, [300, 0, 0])
    assert result['golden'] is True
    assert result['prize']['title'] == '金色頂孔頭獎 NT$300'


def test_no_prize_below_all_tiers(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    monkeypatch.setattr(skeeball, 'MIN_MS_BETWEEN_ROLLS', 0)
    _seed_prizes()
    m = _member('loser')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')
    result = _play_full_game(client, [0, 0, 0])
    assert result['prize'] is None


def test_anticheat_rejections(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    monkeypatch.setattr(skeeball, 'MIN_MS_BETWEEN_ROLLS', 0)
    m = _member('cheater')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')
    start = client.post('/api/skeeball/session/start').get_json()
    sid, nonce = start['sessionId'], start['nonce']

    bad = dict(rollIndex=1, pinsHit=1, score=100, nonce='f' * 64, clientTs=1)
    assert client.post(f'/api/skeeball/session/{sid}/roll',
                       json=bad).status_code == 403          # forged nonce
    assert client.post(f'/api/skeeball/session/{sid}/roll', json={
        **bad, 'nonce': nonce, 'score': 9999}).status_code == 422  # implausible
    assert client.post(f'/api/skeeball/session/{sid}/roll', json={
        **bad, 'nonce': nonce, 'rollIndex': 2}).status_code == 409  # sequence
    # someone else's session is invisible
    other = _member('cheater2')
    _login(client, other['id'])
    assert client.post(f'/api/skeeball/session/{sid}/roll', json={
        **bad, 'nonce': nonce}).status_code == 409


def test_roll_rate_limit(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    m = _member('speedy')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')
    start = client.post('/api/skeeball/session/start').get_json()
    sid, nonce = start['sessionId'], start['nonce']
    roll = dict(pinsHit=0, score=0, nonce=nonce, clientTs=1)
    assert client.post(f'/api/skeeball/session/{sid}/roll',
                       json={**roll, 'rollIndex': 1}).status_code == 200
    assert client.post(f'/api/skeeball/session/{sid}/roll',
                       json={**roll, 'rollIndex': 2}).status_code == 429


def test_complete_idempotent_single_grant(client, monkeypatch):
    monkeypatch.setenv('SKEEBALL_BETA_MEMBERS', 'all')
    monkeypatch.setattr(skeeball, 'MIN_MS_BETWEEN_ROLLS', 0)
    _seed_prizes()
    m = _member('repeat')
    _login(client, m['id'])
    memberdb.skeeball_grant_tokens(m['id'], 1, 'test')
    start = client.post('/api/skeeball/session/start').get_json()
    sid, nonce = start['sessionId'], start['nonce']
    client.post(f'/api/skeeball/session/{sid}/roll', json={
        'rollIndex': 1, 'pinsHit': 1, 'score': 100, 'nonce': nonce, 'clientTs': 1})
    first = client.post(f'/api/skeeball/session/{sid}/complete').get_json()
    again = client.post(f'/api/skeeball/session/{sid}/complete').get_json()
    assert first['totalScore'] == again['totalScore'] == 100
    grants = [r for r in memberdb.list_coupons(m['id'])
              if r['source'] == 'skeeball' and r['source_ref'] == sid]
    assert len(grants) == 1


def test_config_public_and_no_code_leak(client):
    _seed_prizes()
    cfg = client.get('/api/skeeball/config').get_json()
    assert cfg['maxBallsPerSession'] == 3
    assert 'level' in cfg and cfg['level']['targets']
    text = str(cfg)
    assert 'SKEE-' not in text          # codes never leave the server
    assert any(t['title'].startswith('滾球') for t in cfg['prizes']['tiers'])


def test_admin_level_save_guarded(client, monkeypatch):
    level = skeeball.default_level()
    level['lane']['width'] = 5
    monkeypatch.delenv('SKEEBALL_ADMIN_KEY', raising=False)
    assert client.put('/api/skeeball/admin/config/level',
                      json=level).status_code == 403        # admin disabled
    monkeypatch.setenv('SKEEBALL_ADMIN_KEY', 'sesame')
    assert client.put('/api/skeeball/admin/config/level', json=level,
                      headers={'x-admin-key': 'wrong'}).status_code == 403
    ok = client.put('/api/skeeball/admin/config/level', json=level,
                    headers={'x-admin-key': 'sesame'})
    assert ok.status_code == 200
    assert skeeball.current_level()['lane']['width'] == 5
    level['lane']['width'] = 99                              # out of range
    assert client.put('/api/skeeball/admin/config/level', json=level,
                      headers={'x-admin-key': 'sesame'}).status_code == 422
