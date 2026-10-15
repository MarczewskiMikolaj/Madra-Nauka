import sqlite3
from contextlib import contextmanager
from pathlib import Path
from flask import current_app, g
from werkzeug.exceptions import Conflict
from .services.cloud_state import cloud_state, StateUnavailable


def get_db(*, allow_missing=False):
    if "db" not in g:
        store = cloud_state()
        db = sqlite3.connect(
            ":memory:" if store else current_app.config["DATABASE"],
            timeout=10,
            isolation_level=None,
        )
        if store:
            try:
                refresh_cloud_db(db, allow_missing=allow_missing)
            except BaseException:
                db.close()
                raise
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        g.db = db
    return g.db


def refresh_cloud_db(db, *, allow_missing=False):
    data, generation = cloud_state().read("state.sqlite3")
    if data:
        db.deserialize(data)
    elif not allow_missing:
        current_app.logger.warning("Cloud database snapshot is missing")
        raise StateUnavailable()
    g.cloud_generation = generation
    db.execute("PRAGMA foreign_keys=ON")


def publish_cloud_db(db):
    g.cloud_generation = cloud_state().write(
        "state.sqlite3", db.serialize(), g.cloud_generation
    )


@contextmanager
def read_snapshot():
    """Consistent exports without republishing unchanged cloud state."""
    db = get_db()
    db.execute("BEGIN")
    try:
        yield db
    finally:
        db.execute("ROLLBACK")


@contextmanager
def transaction():
    store = cloud_state()
    if store:
        store.lock.acquire()
    try:
        db = get_db()
        if store:
            refresh_cloud_db(db)
        db.execute("BEGIN IMMEDIATE")
        try:
            # Authentication may have happened before another request changed
            # the password or removed the account. Recheck under the write lock.
            user = g.get("user")
            if user:
                fresh = db.execute(
                    "SELECT u.id,COALESCE(p.session_version,0) version FROM users u "
                    "LEFT JOIN user_profiles p ON p.user_id=u.id WHERE u.id=?",
                    (user["id"],),
                ).fetchone()
                if not fresh or fresh["version"] != user["session_version"]:
                    raise Conflict()
            yield db
            db.execute("COMMIT")
            if store:
                publish_cloud_db(db)
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            elif store:
                refresh_cloud_db(db)
            raise
    finally:
        if store:
            store.lock.release()


def init_db():
    db = get_db(allow_missing=True)
    if not cloud_state():
        db.execute("PRAGMA journal_mode=WAL")
    migrated = False
    for version, filename in [
        (1, "001_initial.sql"),
        (2, "002_uploads.sql"),
        (3, "003_ai_jobs.sql"),
        (4, "004_original_files.sql"),
        (5, "005_ai_progress.sql"),
        (6, "006_account_settings.sql"),
        (7, "007_email.sql"),
        (8, "008_student_learning.sql"),
        (9, "009_student_workflow.sql"),
    ]:
        if db.execute("PRAGMA user_version").fetchone()[0] < version:
            migrated = True
            db.executescript(
                (Path(__file__).with_name("migrations") / filename).read_text()
            )
    if cloud_state() and migrated:
        publish_cloud_db(db)


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    import os
    import click

    @app.cli.command("backup-db")
    @click.argument("destination", type=click.Path(path_type=Path))
    def backup_db(destination):
        """Write an exclusive, consistent SQLite backup (contains private data)."""
        if destination.resolve() == Path(current_app.config["DATABASE"]).resolve():
            raise click.ClickException(
                "Destination must differ from the live database."
            )
        try:
            descriptor = os.open(
                destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
        except OSError as error:
            raise click.ClickException(str(error)) from error
        os.close(descriptor)
        try:
            target = sqlite3.connect(destination)
            try:
                get_db().backup(target)
                if (
                    target.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                    or target.execute("PRAGMA foreign_key_check").fetchall()
                ):
                    raise click.ClickException("Backup integrity check failed.")
            finally:
                target.close()
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        click.echo(f"Backup verified: {destination}")

    @app.cli.command("verify-backup")
    @click.argument(
        "source", type=click.Path(exists=True, dir_okay=False, path_type=Path)
    )
    def verify_backup(source):
        """Check backup integrity without modifying it."""
        connection = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if (
                not 1 <= version <= 9
                or connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                raise click.ClickException("Backup integrity or schema check failed.")
            connection.execute("SELECT COUNT(*) FROM users").fetchone()
        except sqlite3.Error as error:
            raise click.ClickException("Not a valid application backup.") from error
        finally:
            connection.close()
        click.echo(f"Backup valid; schema {version}.")
