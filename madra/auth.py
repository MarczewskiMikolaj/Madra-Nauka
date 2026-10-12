import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from functools import wraps
from uuid import uuid4
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db, transaction
from .services.learning import now_iso

bp = Blueprint("auth", __name__)

USER_QUERY = """SELECT users.*,
    COALESCE(user_profiles.session_version, 0) AS session_version,
    user_profiles.avatar_png IS NOT NULL AS has_avatar
    FROM users LEFT JOIN user_profiles ON users.id=user_profiles.user_id"""


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(32)
    return session["csrf"]


def login_required(view):
    @wraps(view)
    def protected(*args, **kwargs):
        if not g.user:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return protected


def init_app(app):
    @app.before_request
    def authenticate():
        g.user = None
        if session.get("user_id"):
            g.user = (
                get_db()
                .execute(USER_QUERY + " WHERE users.id=?", (session["user_id"],))
                .fetchone()
            )
            if (
                not g.user
                or session.get("session_version", 0) != g.user["session_version"]
            ):
                session.clear()
                g.user = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            token = request.form.get("csrf_token") or request.headers.get(
                "X-CSRF-Token", ""
            )
            if not token or not hmac.compare_digest(
                str(token), session.get("csrf", "")
            ):
                abort(400)

    app.jinja_env.globals["csrf_token"] = csrf_token


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("planning.today"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        key = hmac.new(
            current_app.secret_key.encode(),
            f"{request.remote_addr}:{username.casefold()}".encode(),
            hashlib.sha256,
        ).hexdigest()
        timestamp = time.time()
        attempt = (
            get_db()
            .execute("SELECT * FROM login_attempts WHERE key=?", (key,))
            .fetchone()
        )
        if attempt and timestamp - attempt["first_at"] < 900 and attempt["count"] >= 10:
            abort(429)
        user = (
            get_db()
            .execute(USER_QUERY + " WHERE username=? AND is_demo=0", (username,))
            .fetchone()
        )
        if user and check_password_hash(user["password_hash"], password):
            with transaction() as db:
                # Recheck after acquiring the write lock (including a cloud refresh).
                user = db.execute(
                    USER_QUERY + " WHERE users.id=? AND username=? AND is_demo=0",
                    (user["id"], username),
                ).fetchone()
                if not user or not check_password_hash(user["password_hash"], password):
                    abort(409)
                db.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            session.clear()
            session["user_id"] = user["id"]
            session["session_version"] = user["session_version"]
            return redirect(url_for("planning.today"))
        with transaction() as db:
            if not attempt or timestamp - attempt["first_at"] >= 900:
                db.execute(
                    "INSERT OR REPLACE INTO login_attempts VALUES (?,1,?)",
                    (key, timestamp),
                )
            else:
                db.execute(
                    "UPDATE login_attempts SET count=count+1 WHERE key=?", (key,)
                )
        flash("Nieprawidłowa nazwa użytkownika lub hasło.", "error")
    return render_template("auth.html", register=False)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("planning.today"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not re.fullmatch(r"[\w .-]{3,40}", username):
            flash(
                "Nazwa musi mieć 3–40 znaków: litery, cyfry, spacje, kropki lub myślniki.",
                "error",
            )
        elif not 8 <= len(password) <= 256:
            flash("Hasło musi mieć od 8 do 256 znaków.", "error")
        elif password != request.form.get("confirm_password"):
            flash("Hasła nie są takie same.", "error")
        else:
            uid = uuid4().hex
            try:
                with transaction() as db:
                    db.execute(
                        "INSERT INTO users VALUES (?,?,?,0,?)",
                        (uid, username, generate_password_hash(password), now_iso()),
                    )
            except sqlite3.IntegrityError:
                flash("Ta nazwa użytkownika jest już zajęta.", "error")
            else:
                session.clear()
                session["user_id"] = uid
                flash(
                    "Twoja przestrzeń jest gotowa. Dodaj pierwszy przedmiot.", "success"
                )
                return redirect(url_for("library.index"))
    return render_template("auth.html", register=True)


@bp.post("/demo")
def demo():
    if not current_app.config["ALLOW_DEMO"]:
        abort(404)
    if g.user:
        return redirect(url_for("planning.today"))
    from .services.demo import create_demo

    uid = create_demo()
    session.clear()
    session["user_id"] = uid
    return redirect(url_for("planning.today"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("planning.landing"))
