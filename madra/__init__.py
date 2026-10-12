import os
import secrets
import sqlite3
import logging
from pathlib import Path
from flask import Flask, render_template
from . import db


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.logger.setLevel(logging.INFO)
    production = os.environ.get("MADRA_ENV") == "production"
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "MADRA_DATABASE_PATH", str(Path(app.instance_path) / "madra.sqlite3")
        ),
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        TIMEZONE="Europe/Warsaw",
        ALLOW_DEMO=not production,
        CHATGPT_LOCAL_AUTH=not production,
        CHATGPT_CALLBACK_URL="http://127.0.0.1:"
        + os.environ.get("PORT", "8080")
        + "/auth/callback",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        MAX_CONTENT_LENGTH=11 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        if production:
            raise RuntimeError("Set SECRET_KEY before starting in production.")
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        secret_path = Path(app.instance_path) / "secret.key"
        try:
            fd = os.open(secret_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w") as f:
                f.write(secrets.token_hex(32))
        app.config["SECRET_KEY"] = secret_path.read_text().strip()
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(db.close_db)
    from . import auth, library, study, planning, uploads, ai
    from .services import migration

    for blueprint in (auth.bp, library.bp, study.bp, planning.bp, uploads.bp, ai.bp):
        app.register_blueprint(blueprint)
    auth.init_app(app)
    migration.init_app(app)

    from .services.notes import note_chapters

    app.jinja_env.filters["note_chapters"] = note_chapters

    @app.context_processor
    def vocabulary():
        from .services.learning import KINDS, DIMENSIONS

        return {"kinds": KINDS, "dimensions": DIMENSIONS}

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://auth.openai.com"
        )
        if response.mimetype in ("text/html", "application/json"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error_page(error):
        messages = {
            400: "Nieprawidłowy formularz. Odśwież stronę i spróbuj ponownie.",
            403: "Nie masz dostępu do tej strony.",
            404: "Nie znaleźliśmy tej strony.",
            409: "Stan sesji się zmienił. Wróć do nauki i odśwież stronę.",
            413: "Materiał jest za duży. Maksymalny rozmiar pliku to 10 MB.",
            429: "Za dużo prób logowania. Spróbuj ponownie za 15 minut.",
        }
        return (
            render_template(
                "error.html", code=error.code, message=messages[error.code]
            ),
            error.code,
        )

    @app.errorhandler(sqlite3.Error)
    def storage_error(error):
        app.logger.exception("Database operation failed")
        return (
            render_template(
                "error.html",
                code=503,
                message="Nie udało się zapisać danych. Spróbuj ponownie.",
            ),
            503,
        )

    @app.get("/health")
    def health():
        db.get_db().execute("SELECT 1").fetchone()
        return {"status": "ok", "version": "2.0-mvp"}

    with app.app_context():
        db.init_db()
    ai.init_app(app)
    return app
