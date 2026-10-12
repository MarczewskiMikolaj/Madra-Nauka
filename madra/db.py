import sqlite3
from contextlib import contextmanager
from pathlib import Path
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"], timeout=10, isolation_level=None
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=10000")
    return g.db


@contextmanager
def transaction():
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    try:
        yield db
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def init_db():
    db = get_db()
    db.execute("PRAGMA journal_mode=WAL")
    for version, filename in [
        (1, "001_initial.sql"),
        (2, "002_uploads.sql"),
        (3, "003_ai_jobs.sql"),
        (4, "004_original_files.sql"),
        (5, "005_ai_progress.sql"),
    ]:
        if db.execute("PRAGMA user_version").fetchone()[0] < version:
            db.executescript(
                (Path(__file__).with_name("migrations") / filename).read_text()
            )


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
