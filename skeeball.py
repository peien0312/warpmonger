"""荷魯斯滾球 (HORUS BALL) — skeeball mini-game API.

Python port of the HORUSBALL Express backend (github.com/max92034/HORUSBALL,
INTEGRATION.md strategy B): the game frontend is a static Vite build served
at /game; this blueprint serves the same endpoint contract under
/api/skeeball. Differences from the original:

- Auth = site member session (session['member_id']); no game-side accounts.
- Wallet = memberdb.skeeball_wallet. Tokens are manually granted (closed
  beta); 1 token = one 3-ball game.
- Direct prize model (no ticket currency / prize booth): on complete the
  server-recomputed total maps through prize tiers (POS settings key
  'skeeball_prizes') straight to a coupon grant in the member's wallet
  (source 'skeeball', source_ref session id → exactly-once per game).
  A single-roll apex hit (the top hole) wins the jackpot tier instead.
- Level config saved by the in-game editor lives in memberdb.skeeball_kv
  ('level'), guarded by SKEEBALL_ADMIN_KEY.

Prize coupons must exist in the POS coupons table with auto_grant =
'skeeball' — checkout already refuses typed-in codes for system-granted
coupons, so a screenshot of a win can't be replayed by other members.
"""
import hashlib
import hmac
import json
import os
import re
import time
import uuid

from flask import Blueprint, jsonify, request, session

import memberdb

bp = Blueprint("skeeball", __name__, url_prefix="/api/skeeball")

MAX_BALLS = 3
SESSION_MAX_MS = 10 * 60 * 1000
MIN_MS_BETWEEN_ROLLS = 500
APEX_POINTS = 300           # single-roll score that counts as a jackpot hit

PRIZES_SETTING_KEY = "skeeball_prizes"   # POS settings: {"tiers":[{"min_score":..,"code":..}],"apex_code":..}


# ----- beta gate -----

def beta_allowed(member_id):
    """Closed-beta allowlist from env SKEEBALL_BETA_MEMBERS: comma-separated
    member ids, or 'all' to open to every logged-in member. Empty/unset =
    feature off."""
    raw = (os.environ.get("SKEEBALL_BETA_MEMBERS") or "").strip()
    if not raw or not member_id:
        return False
    if raw.lower() == "all":
        return True
    return str(member_id) in {p.strip() for p in raw.split(",") if p.strip()}


def _member_id_or_none():
    mid = session.get("member_id")
    if not mid or not beta_allowed(mid):
        return None
    return mid


def free_play():
    """Env SKEEBALL_FREE_PLAY=1: games cost no tokens (beta unlimited mode).
    Unset it to return to the token economy at launch."""
    return (os.environ.get("SKEEBALL_FREE_PLAY") or "").strip().lower() in ("1", "true", "yes")


# ----- level config (defaults mirror HORUSBALL backend/models/Config.js) -----

def default_level():
    """Mirror of the frontend DEFAULT_LEVEL (levelConfig.js) — tilted target
    deck, easy 50 in the landing path, golden 300s in the top corners."""
    return {
        "targets": [
            {"name": "中央之門 50", "points": 50, "r": 0.85, "x": 0, "y": 3.0, "color": "#38bdf8"},
            {"name": "左聖印 100", "points": 100, "r": 0.7, "x": -1.5, "y": 3.7, "color": "#a78bfa"},
            {"name": "右聖印 100", "points": 100, "r": 0.7, "x": 1.5, "y": 3.7, "color": "#a78bfa"},
            {"name": "帝皇之眼 150", "points": 150, "r": 0.66, "x": 0, "y": 4.5, "color": "#f59e0b"},
            {"name": "荷魯斯之眼 L", "points": 300, "r": 0.62, "x": -1.85, "y": 5.2, "color": "#facc15"},
            {"name": "荷魯斯之眼 R", "points": 300, "r": 0.62, "x": 1.85, "y": 5.2, "color": "#facc15"},
        ],
        "lane": {"width": 4, "length": 12, "thickness": 0.3},
        "ramp": {"length": 3.5, "rise": 2.2, "gap": 1.0, "curve": 0.45},
        "backboard": {"height": 4, "thickness": 0.25, "tilt": 0.62},
        "ball": {"radius": 0.4, "mass": 2.5, "friction": 0.9, "restitution": 0.22,
                 "minSpeed": 14, "maxSpeed": 26, "upBase": 0.04, "upScale": 0.05},
        "aim": {"maxAngle": 0.14, "oscSpeed": 1.6},
        "textures": {"ballUrl": "/static/game/tex/wh_ball.jpg",
                     "laneUrl": "/static/game/tex/wh_lane.jpg",
                     "backgroundUrl": "/static/game/tex/wh_space.jpg"},
    }


def current_level():
    return memberdb.skeeball_kv_get("level") or default_level()


def _max_plausible_score():
    try:
        return max(t["points"] for t in current_level()["targets"])
    except Exception:
        return APEX_POINTS


# ----- prize tiers (definitions in POS settings + coupons table) -----

def prize_config():
    import posdb
    cfg = posdb._setting_json(PRIZES_SETTING_KEY, {})
    return cfg if isinstance(cfg, dict) else {}


def _coupon_brief(code):
    import posdb
    c = posdb.get_coupon((code or "").strip().upper())
    if not c or not c.get("active"):
        return None
    return {"code": c["code"], "title": c.get("title") or c["code"],
            "amount_twd": int(c.get("amount_twd") or 0)}


def prize_display():
    """Tier list for the frontend scoreboard: what score wins what.
    Codes are stripped — /config is public."""
    def pub(c):
        return {"title": c["title"], "amount_twd": c["amount_twd"]} if c else None

    cfg = prize_config()
    tiers = []
    for t in sorted(cfg.get("tiers") or [], key=lambda t: -(t.get("min_score") or 0)):
        c = pub(_coupon_brief(t.get("code")))
        if c:
            tiers.append({"minScore": int(t.get("min_score") or 0), **c})
    return {"tiers": tiers, "apex": pub(_coupon_brief(cfg.get("apex_code")))}


def pick_prize(total_score, golden):
    """Direct prize mapping: apex hit → jackpot coupon, else best tier whose
    min_score the total reaches. Returns coupon brief or None."""
    cfg = prize_config()
    if golden:
        apex = _coupon_brief(cfg.get("apex_code"))
        if apex:
            return apex
    best = None
    for t in cfg.get("tiers") or []:
        ms = int(t.get("min_score") or 0)
        if total_score >= ms and (best is None or ms > best[0]):
            c = _coupon_brief(t.get("code"))
            if c:
                best = (ms, c)
    return best[1] if best else None


# ----- session storage helpers -----

def _get_session(sid, member_id):
    conn = memberdb._conn()
    row = conn.execute(
        "SELECT * FROM skeeball_sessions WHERE id = ? AND member_id = ?",
        (sid, member_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def _update_session(sid, **fields):
    keys = ", ".join(f"{k} = ?" for k in fields)
    conn = memberdb._conn()
    conn.execute(f"UPDATE skeeball_sessions SET {keys} WHERE id = ?",
                 (*fields.values(), sid))
    conn.commit()
    conn.close()


def _sign_nonce(sid, secret):
    return hmac.new(secret.encode(), sid.encode(), hashlib.sha256).hexdigest()


# ----- endpoints (contract: HORUSBALL INTEGRATION.md §4) -----

@bp.get("/config")
def config():
    return jsonify({
        "tokenCostPerGame": 1,
        "maxBallsPerSession": MAX_BALLS,
        "scoreToTicketRates": [],   # ticket economy unused (direct prizes)
        "assetCatalog": [],
        "level": current_level(),
        "prizes": prize_display(),
    })


@bp.get("/user/balance")
def balance():
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({
        "tokenBalance": memberdb.skeeball_tokens(mid),
        "freePlay": free_play(),
        "ticketBalance": 0,
        "goldenTickets": 0,
        "customAssets": {},
        "unlockedAssets": [],
    })


@bp.post("/session/start")
def start():
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    spent = False
    if not free_play():
        if not memberdb.skeeball_spend_token(mid):
            return jsonify({"error": "insufficient_tokens"}), 402
        spent = True

    sid = uuid.uuid4().hex
    secret = uuid.uuid4().hex + uuid.uuid4().hex
    expires_at = time.time() + SESSION_MAX_MS / 1000
    try:
        conn = memberdb._conn()
        conn.execute(
            "INSERT INTO skeeball_sessions (id, member_id, secret, expires_at) "
            "VALUES (?, ?, ?, ?)", (sid, mid, secret, expires_at))
        conn.commit()
        conn.close()
    except Exception:
        if spent:
            memberdb.skeeball_refund_token(mid)
        raise
    return jsonify({
        "sessionId": sid,
        "nonce": _sign_nonce(sid, secret),
        "maxBalls": MAX_BALLS,
        "expiresAt": int(expires_at * 1000),
    }), 201


@bp.post("/session/<sid>/roll")
def roll(sid):
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    roll_index, pins_hit, score = data.get("rollIndex"), data.get("pinsHit"), data.get("score")
    nonce, client_ts = data.get("nonce"), data.get("clientTs")
    if (not isinstance(roll_index, int) or not isinstance(pins_hit, int)
            or not isinstance(score, int) or isinstance(score, bool)
            or not isinstance(nonce, str)
            or not isinstance(client_ts, (int, float))):
        return jsonify({"error": "invalid_payload"}), 400

    s = _get_session(sid, mid)
    if not s or s["status"] != "active":
        return jsonify({"error": "session_not_active"}), 409

    if not hmac.compare_digest(nonce, _sign_nonce(sid, s["secret"])):
        return jsonify({"error": "invalid_nonce"}), 403
    if roll_index != s["balls_thrown"] + 1:
        return jsonify({"error": "roll_out_of_sequence"}), 409
    if roll_index > MAX_BALLS or score < 0 or score > _max_plausible_score():
        return jsonify({"error": "implausible_roll"}), 422
    now_ms = time.time() * 1000
    if now_ms > (s["expires_at"] or 0) * 1000:
        _update_session(sid, status="expired")
        return jsonify({"error": "session_expired"}), 410
    rolls = json.loads(s["rolls"])
    if rolls and now_ms - rolls[-1]["serverTs"] < MIN_MS_BETWEEN_ROLLS:
        return jsonify({"error": "rolls_too_fast"}), 429

    rolls.append({"rollIndex": roll_index, "pinsHit": pins_hit, "score": score,
                  "clientTs": client_ts, "serverTs": now_ms})
    golden = s["golden"] or (1 if score == APEX_POINTS else 0)
    _update_session(sid, rolls=json.dumps(rolls),
                    balls_thrown=s["balls_thrown"] + 1, golden=golden)
    return jsonify({"accepted": True, "ballsThrown": s["balls_thrown"] + 1,
                    "maxBalls": MAX_BALLS})


@bp.post("/session/<sid>/complete")
def complete(sid):
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    s = _get_session(sid, mid)
    if not s:
        return jsonify({"error": "not_found"}), 404
    if s["status"] == "completed":
        prize = _coupon_brief(s["prize_code"]) if s["prize_code"] else None
        return jsonify({"totalScore": s["total_score"], "ticketsAwarded": 0,
                        "golden": bool(s["golden"]), "prize": prize})
    if s["status"] != "active":
        return jsonify({"error": "session_not_active"}), 409

    # Never trust client totals — recompute from the server-stamped roll log
    rolls = json.loads(s["rolls"])
    total = sum(r["score"] for r in rolls)
    prize = pick_prize(total, bool(s["golden"]))
    granted = None
    if prize:
        if memberdb.grant_coupon(mid, prize["code"], "skeeball", sid):
            granted = prize
    _update_session(sid, status="completed", total_score=total,
                    prize_code=(granted or {}).get("code"),
                    prize_title=(granted or {}).get("title"),
                    ended_at=time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
    return jsonify({"totalScore": total, "ticketsAwarded": 0,
                    "golden": bool(s["golden"]), "prize": granted})


@bp.get("/leaderboard")
def leaderboard():
    """本週排行榜 — best completed-session score per member, rolling 7 days.
    Names are masked; the caller's own row is flagged. Beta-gated like the
    rest of the game API."""
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    conn = memberdb._conn()
    rows = conn.execute("""
        SELECT s.member_id, MAX(s.total_score) AS best, COUNT(*) AS games,
               COALESCE(m.name, '') AS name
        FROM skeeball_sessions s
        JOIN members m ON m.id = s.member_id
        WHERE s.status = 'completed'
          AND s.started_at >= datetime('now', '-7 day')
          AND s.total_score > 0
        GROUP BY s.member_id
        ORDER BY best DESC, games ASC
        LIMIT 10
    """).fetchall()
    conn.close()

    def mask(name):
        name = (name or "").strip()
        return (name[0] + "○○") if name else "神秘玩家"

    return jsonify({"entries": [
        {"rank": i + 1, "name": mask(r["name"]), "best": r["best"],
         "games": r["games"], "me": r["member_id"] == mid}
        for i, r in enumerate(rows)
    ]})


@bp.get("/session/<sid>")
def get_session(sid):
    mid = _member_id_or_none()
    if not mid:
        return jsonify({"error": "unauthorized"}), 401
    s = _get_session(sid, mid)
    if not s:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"sessionId": s["id"], "status": s["status"],
                    "ballsThrown": s["balls_thrown"],
                    "totalScore": s["total_score"],
                    "expiresAt": int((s["expires_at"] or 0) * 1000)})


# ----- level editor save (port of backend/routes/admin.js) -----

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# http(s) or site-relative (the bundled /static/game/tex/* skins)
_URL_RE = re.compile(r"^(https?://.+|/[^/].*)")


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def sanitize_level(body):
    """Validate + whitelist a level payload. Returns (level, None) or (None, error)."""
    if not isinstance(body, dict):
        return None, "level object required"
    targets_in = body.get("targets")
    if not isinstance(targets_in, list) or not 1 <= len(targets_in) <= 8:
        return None, "targets must be an array of 1-8 items"
    targets = []
    for t in targets_in:
        if not isinstance(t, dict):
            return None, "each target must be an object"
        if not isinstance(t.get("name"), str) or not t["name"].strip():
            return None, "target.name must be a non-empty string"
        p = t.get("points")
        if not isinstance(p, int) or isinstance(p, bool) or not 10 <= p <= 999:
            return None, "target.points must be an integer 10-999"
        if not _num(t.get("r"), 0.2, 1.2):
            return None, "target.r must be 0.2-1.2"
        if not _num(t.get("x"), -2.4, 2.4):
            return None, "target.x must be within [-2.4, 2.4]"
        if not _num(t.get("y"), 2.2, 6.0):
            return None, "target.y must be within [2.2, 6.0]"
        if not isinstance(t.get("color"), str) or not _COLOR_RE.match(t["color"]):
            return None, "target.color must be a #rrggbb hex string"
        targets.append({k: t[k] for k in ("name", "points", "r", "x", "y", "color")})

    def section(obj, rules, label):
        if not isinstance(obj, dict):
            return None, f"{label} object required"
        out = {}
        for k, (lo, hi) in rules.items():
            if not _num(obj.get(k), lo, hi):
                return None, f"{label}.{k} must be {lo}-{hi}"
            out[k] = obj[k]
        return out, None

    lane, err = section(body.get("lane"), {"width": (2, 6), "length": (6, 20), "thickness": (0.1, 0.6)}, "lane")
    if err:
        return None, err
    ramp, err = section(body.get("ramp"), {"length": (1.5, 6), "rise": (0.5, 4), "gap": (0, 4), "curve": (0, 1)}, "ramp")
    if err:
        return None, err
    backboard, err = section(body.get("backboard"), {"height": (2, 8), "thickness": (0.1, 0.5), "tilt": (0, 1.2)}, "backboard")
    if err:
        return None, err
    ball, err = section(body.get("ball"), {
        "radius": (0.2, 0.6), "mass": (0.5, 10), "friction": (0, 2),
        "restitution": (0, 1), "minSpeed": (0.5, 20),
        "maxSpeed": (float("-inf"), 40), "upBase": (0, 0.3), "upScale": (0, 0.5),
    }, "ball")
    if err:
        return None, err
    if not ball["maxSpeed"] > ball["minSpeed"]:
        return None, "ball.maxSpeed must be greater than ball.minSpeed"
    aim, err = section(body.get("aim"), {"maxAngle": (0.05, 0.8), "oscSpeed": (0.2, 5)}, "aim")
    if err:
        return None, err

    tex_in = body.get("textures")
    if not isinstance(tex_in, dict):
        return None, "textures object required"
    textures = {}
    for k in ("ballUrl", "laneUrl", "backgroundUrl"):
        v = tex_in.get(k)
        if not isinstance(v, str) or len(v) > 500 or (v != "" and not _URL_RE.match(v)):
            return None, f"textures.{k} must be '' or an http(s) URL up to 500 chars"
        textures[k] = v

    return {"targets": targets, "lane": lane, "ramp": ramp,
            "backboard": backboard, "ball": ball, "aim": aim,
            "textures": textures}, None


@bp.put("/admin/config/level")
def admin_save_level():
    key = os.environ.get("SKEEBALL_ADMIN_KEY")
    if not key:
        return jsonify({"error": "admin disabled"}), 403
    if request.headers.get("x-admin-key") != key:
        return jsonify({"error": "forbidden"}), 403
    level, err = sanitize_level(request.get_json(silent=True))
    if err:
        return jsonify({"error": err}), 422
    memberdb.skeeball_kv_set("level", level)
    return jsonify({"level": level})
