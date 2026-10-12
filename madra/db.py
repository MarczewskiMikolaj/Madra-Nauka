import sqlite3
from contextlib import contextmanager
from pathlib import Path
from flask import current_app, g
from .services.cloud_state import cloud_state


def get_db():
    if "db" not in g:
        store = cloud_state()
        g.db = sqlite3.connect(
            ":memory:" if store else current_app.config["DATABASE"],
            timeout=10,
            isolation_level=None,
        )
        if store:
            refresh_cloud_db(g.db)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA busy_timeout=10000")
    return g.db


def refresh_cloud_db(db):
    data, generation = cloud_state().read("state.sqlite3")
    if data:
        db.deserialize(data)
    g.cloud_generation = generation
    db.execute("PRAGMA foreign_keys=ON")


def publish_cloud_db(db):
    g.cloud_generation = cloud_state().write(
        "state.sqlite3", db.serialize(), g.cloud_generation
    )


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
    db = get_db()
    if not cloud_state():
        db.execute("PRAGMA journal_mode=WAL")
    migrated = False
    for version, filename in [
        (1, "001_initial.sql"),
        (2, "002_uploads.sql"),
        (3, "003_ai_jobs.sql"),
        (4, "004_original_files.sql"),
        (5, "005_ai_progress.sql"),
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
