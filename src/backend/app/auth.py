"""Простая авторизация: email + пароль, подписанный токен (Bearer)."""
import re
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from . import db as dbmod

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _ser():
    return URLSafeTimedSerializer(current_app.config["CFG"].secret_key, salt="lebensgeschichte-auth")


def make_token(user_id):
    return _ser().dumps({"uid": user_id})


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        token = header[7:] if header.startswith("Bearer ") else request.args.get("token", "")
        if not token:
            return jsonify(error="unauthorized"), 401
        try:
            data = _ser().loads(token, max_age=current_app.config["CFG"].token_ttl_hours * 3600)
        except (BadSignature, SignatureExpired):
            return jsonify(error="unauthorized"), 401
        row = dbmod.get_db().execute("SELECT id FROM users WHERE id=?", (data["uid"],)).fetchone()
        if row is None:
            return jsonify(error="unauthorized"), 401
        g.user_id = row["id"]
        return fn(*args, **kwargs)
    return wrapper


def _creds():
    body = request.get_json(silent=True) or {}
    return (body.get("email") or "").strip().lower(), body.get("password") or ""


@bp.post("/register")
def register():
    cfg = current_app.config["CFG"]
    if not cfg.registration_open:
        return jsonify(error="registration_closed"), 403
    email, password = _creds()
    if not EMAIL_RE.match(email):
        return jsonify(error="invalid_email"), 400
    if len(password) < 8:
        return jsonify(error="password_too_short"), 400
    db = dbmod.get_db()
    if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        return jsonify(error="email_taken"), 409
    cur = db.execute("INSERT INTO users(email,pw_hash,created_at) VALUES(?,?,?)",
                     (email, generate_password_hash(password), dbmod.now()))
    db.commit()
    return jsonify(token=make_token(cur.lastrowid)), 201


@bp.post("/login")
def login():
    email, password = _creds()
    row = dbmod.get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if row is None or not check_password_hash(row["pw_hash"], password):
        return jsonify(error="invalid_credentials"), 401
    return jsonify(token=make_token(row["id"]))
