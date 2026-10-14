"""Private account settings; profile data shares the durable SQLite state."""

from io import BytesIO
import re

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

from .auth import USER_QUERY, login_required, consume_attempt
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


def confirm_password(db, user):
    key = consume_attempt(db, "password", user["id"])
    password = request.form.get("current_password", "")
    if not 1 <= len(password) <= 256 or not check_password_hash(
        user["password_hash"], password
    ):
        return False
    db.execute("DELETE FROM login_attempts WHERE key=?", (key,))
    return True


def set_password(db, user, password):
    version = user["session_version"] + 1
    db.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        (generate_password_hash(password), user["id"]),
    )
    db.execute(
        "INSERT INTO user_profiles (user_id,session_version) VALUES (?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET session_version=excluded.session_version",
        (user["id"], version),
    )
    return version


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
    with transaction() as db:
        user = fresh_user(db)
        if not confirm_password(db, user):
            error = "Obecne hasło jest nieprawidłowe."
        elif not error and check_password_hash(user["password_hash"], new_password):
            error = "Nowe hasło musi różnić się od obecnego."
        if error:
            flash(error, "error")
            return render_template("account.html", nav="account"), 400
        version = set_password(db, user, new_password)
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


@bp.post("/konto/usun")
@login_required
def delete_account():
    if g.user["is_demo"]:
        abort(403)
    from .services import chatgpt

    uid = g.user["id"]
    # Serialize with OAuth/token rotation; never delete an account mid-generation.
    with chatgpt.locked(uid), transaction() as db:
        user = fresh_user(db)
        if not confirm_password(db, user):
            flash("Obecne hasło jest nieprawidłowe.", "error")
            return render_template("account.html", nav="account"), 400
        if request.form.get("confirm_username", "") != user["username"]:
            flash("Potwierdź usunięcie, wpisując dokładną nazwę użytkownika.", "error")
            return render_template("account.html", nav="account"), 400
        if db.execute(
            "SELECT 1 FROM ai_jobs WHERE user_id=? AND state='running'", (uid,)
        ).fetchone():
            flash(
                "Poczekaj na zakończenie opracowań AI przed usunięciem konta.", "error"
            )
            return render_template("account.html", nav="account"), 409
        connection = chatgpt.load(uid)
        if connection.get("tokens") or connection.get("pending"):
            flash(
                "Najpierw odłącz ChatGPT w Połączeniu AI, a potem usuń konto.", "error"
            )
            return render_template("account.html", nav="account"), 409
        # Remove identity metadata too; an empty encrypted tombstone is safe to retry.
        chatgpt.save(uid, {})
        statements = [
            "DELETE FROM activity_imports WHERE user_id=?",
            "DELETE FROM reviews WHERE user_id=?",
            "DELETE FROM session_items WHERE session_id IN (SELECT id FROM study_sessions WHERE user_id=?)",
            "DELETE FROM study_sessions WHERE user_id=?",
            "DELETE FROM progress WHERE user_id=?",
            "DELETE FROM goals WHERE user_id=?",
            "DELETE FROM ai_jobs WHERE user_id=?",
            "DELETE FROM upload_activities WHERE upload_id IN (SELECT id FROM uploads WHERE user_id=?)",
            "DELETE FROM upload_materials WHERE upload_id IN (SELECT id FROM uploads WHERE user_id=?)",
            "DELETE FROM uploads WHERE user_id=?",
            "DELETE FROM activity_support WHERE material_id IN (SELECT m.id FROM materials m JOIN topics t ON t.id=m.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?)",
            "DELETE FROM activities WHERE topic_id IN (SELECT t.id FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?)",
            "DELETE FROM materials WHERE topic_id IN (SELECT t.id FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?)",
            "DELETE FROM topics WHERE workspace_id IN (SELECT id FROM workspaces WHERE user_id=?)",
            "DELETE FROM legacy_payloads WHERE workspace_id IN (SELECT id FROM workspaces WHERE user_id=?)",
            "DELETE FROM workspaces WHERE user_id=?",
            "DELETE FROM users WHERE id=?",
        ]
        for sql in statements:
            db.execute(sql, (uid,))
    session.clear()
    flash(
        "Konto i jego materiały, pliki oraz historia zostały usunięte z aplikacji.",
        "success",
    )
    return redirect(url_for("planning.landing"))
