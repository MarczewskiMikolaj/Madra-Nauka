"""Private account settings; profile data shares the durable SQLite state."""

from io import BytesIO
import re
import time

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
    Response,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.security import check_password_hash, generate_password_hash

from .auth import USER_QUERY, login_required
from .db import get_db, transaction

bp = Blueprint("account", __name__)
MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_PIXELS = 16_000_000


def fresh_user(db):
    """Check session validity again under the transaction's write lock."""
    user = db.execute(USER_QUERY + " WHERE users.id=?", (g.user["id"],)).fetchone()
    if not user or user["session_version"] != session.get("session_version", 0):
        abort(409)
    return user


def prepare_avatar(upload):
    if not upload or not upload.filename:
        raise ValueError("Wybierz zdjęcie w formacie JPG, PNG lub WebP.")
    data = upload.read(MAX_AVATAR_BYTES + 1)
    if len(data) > MAX_AVATAR_BYTES:
        raise ValueError("Zdjęcie jest za duże. Wybierz plik do 2 MB.")
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG", "WEBP")) as image:
            if image.width * image.height > MAX_AVATAR_PIXELS:
                raise ValueError(
                    "Zdjęcie ma za dużą rozdzielczość. Maksymalnie 16 megapikseli."
                )
            image.load()
            image = ImageOps.exif_transpose(image)
            cropped = ImageOps.fit(
                image.convert("RGBA"), (256, 256), method=Image.Resampling.LANCZOS
            )
            # Copy pixels into a fresh image to discard EXIF and other metadata.
            clean = Image.new("RGBA", cropped.size)
            clean.paste(cropped)
            output = BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as error:
        raise ValueError(
            "Nie można odczytać zdjęcia. Wybierz poprawny plik JPG, PNG lub WebP."
        ) from error


@bp.get("/konto")
@login_required
def settings():
    return render_template("account.html", nav="account")


@bp.post("/konto/profil")
@login_required
def profile():
    if g.user["is_demo"]:
        abort(403)
    username = request.form.get("username", "").strip()
    if not re.fullmatch(r"[\w .-]{3,40}", username):
        flash(
            "Nazwa musi mieć 3–40 znaków: litery, cyfry, spacje, kropki lub myślniki.",
            "error",
        )
        return render_template("account.html", nav="account"), 400
    with transaction() as db:
        fresh_user(db)
        if db.execute(
            "SELECT id FROM users WHERE username=? AND id<>?", (username, g.user["id"])
        ).fetchone():
            flash("Ta nazwa użytkownika jest już zajęta.", "error")
            return render_template("account.html", nav="account"), 400
        db.execute("UPDATE users SET username=? WHERE id=?", (username, g.user["id"]))
    flash(
        "Nazwa użytkownika została zmieniona. Użyj jej przy kolejnym logowaniu.",
        "success",
    )
    return redirect(url_for("account.settings"))


@bp.post("/konto/haslo")
@login_required
def password():
    if g.user["is_demo"]:
        abort(403)
    new_password = request.form.get("new_password", "")
    error = None
    if not 8 <= len(new_password) <= 256:
        error = "Hasło musi mieć od 8 do 256 znaków."
    elif new_password != request.form.get("confirm_password", ""):
        error = "Hasła nie są takie same."
    current_password = request.form.get("current_password", "")
    with transaction() as db:
        user = fresh_user(db)
        key = "password:" + user["id"]
        timestamp = time.time()
        attempt = db.execute(
            "SELECT * FROM login_attempts WHERE key=?", (key,)
        ).fetchone()
        if attempt and timestamp - attempt["first_at"] < 900 and attempt["count"] >= 10:
            abort(429)
        if not 1 <= len(current_password) <= 256 or not check_password_hash(
            user["password_hash"], current_password
        ):
            error = "Obecne hasło jest nieprawidłowe."
            if not attempt or timestamp - attempt["first_at"] >= 900:
                db.execute(
                    "INSERT OR REPLACE INTO login_attempts VALUES (?,1,?)",
                    (key, timestamp),
                )
            else:
                db.execute(
                    "UPDATE login_attempts SET count=count+1 WHERE key=?", (key,)
                )
        else:
            db.execute("DELETE FROM login_attempts WHERE key=?", (key,))
            if not error and check_password_hash(user["password_hash"], new_password):
                error = "Nowe hasło musi różnić się od obecnego."
        if error:
            flash(error, "error")
            return render_template("account.html", nav="account"), 400
        version = user["session_version"] + 1
        db.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (generate_password_hash(new_password), user["id"]),
        )
        db.execute(
            """INSERT INTO user_profiles (user_id, session_version) VALUES (?,?)
            ON CONFLICT(user_id) DO UPDATE SET session_version=excluded.session_version""",
            (user["id"], version),
        )
    session.clear()
    session["user_id"] = user["id"]
    session["session_version"] = version
    flash("Hasło zostało zmienione. Pozostałe sesje zostały wylogowane.", "success")
    return redirect(url_for("account.settings"))


@bp.post("/konto/awatar")
@login_required
def avatar_save():
    if g.user["is_demo"]:
        abort(403)
    remove = request.form.get("action") == "remove"
    try:
        avatar = None if remove else prepare_avatar(request.files.get("avatar"))
    except ValueError as error:
        flash(str(error), "error")
        return render_template("account.html", nav="account"), 400
    with transaction() as db:
        fresh_user(db)
        db.execute(
            """INSERT INTO user_profiles (user_id, avatar_png) VALUES (?,?)
            ON CONFLICT(user_id) DO UPDATE SET avatar_png=excluded.avatar_png""",
            (g.user["id"], avatar),
        )
    flash(
        "Zdjęcie zostało usunięte." if remove else "Zdjęcie zostało zapisane.",
        "success",
    )
    return redirect(url_for("account.settings"))


@bp.get("/konto/awatar")
@login_required
def avatar():
    row = (
        get_db()
        .execute(
            "SELECT avatar_png FROM user_profiles WHERE user_id=?", (g.user["id"],)
        )
        .fetchone()
    )
    if not row or row["avatar_png"] is None:
        abort(404)
    response = Response(row["avatar_png"], mimetype="image/png")
    response.headers["Cache-Control"] = "private, no-store"
    return response
