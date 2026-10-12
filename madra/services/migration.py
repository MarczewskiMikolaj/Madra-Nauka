"""Explicit, transactional legacy import. Dry-run by default."""

import json
import os
from pathlib import Path
from uuid import uuid4
import click
from ..db import get_db, transaction
from .learning import now_iso


def read_users(path):
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        key = os.environ.get("LEGACY_ENCRYPTION_KEY") or os.environ.get(
            "ENCRYPTION_KEY"
        )
        if not key:
            raise ValueError("Encrypted users file requires LEGACY_ENCRYPTION_KEY.")
        from cryptography.fernet import Fernet

        data = json.loads(Fernet(key.encode()).decrypt(raw))
    if isinstance(data, dict) and "users" in data:
        data = data["users"]
    elif isinstance(data, dict):
        data = [{"login": login, **info} for login, info in data.items()]
    if not isinstance(data, list):
        raise ValueError("Invalid users format.")
    return data


def import_legacy(sets_path, users_path=None, owner=None, apply=False):
    data = json.loads(Path(sets_path).read_text())
    sets = data.get("sets", []) if isinstance(data, dict) else data
    if not isinstance(sets, list):
        raise ValueError("Invalid sets format.")
    users = read_users(users_path) if users_path else []
    db = get_db()
    accounts = {
        r["username"].casefold(): r["id"]
        for r in db.execute("SELECT * FROM users WHERE is_demo=0")
    }
    additions = []
    for user in users:
        name = user.get("login", "").strip()
        password = user.get("haslo") or user.get("password")
        if not name or not isinstance(password, str) or not password:
            raise ValueError("An imported account has no login or password hash.")
        existing = db.execute(
            "SELECT * FROM users WHERE username=?", (name,)
        ).fetchone()
        if existing and existing["password_hash"] != password:
            raise ValueError(
                "An existing account conflicts with an imported account. Import stopped."
            )
        if name.casefold() not in accounts:
            uid = uuid4().hex
            accounts[name.casefold()] = uid
            additions.append(
                (uid, name, password, user.get("data_utworzenia") or now_iso())
            )
    if owner and owner.casefold() not in accounts:
        raise ValueError("The specified owner account does not exist.")
    imports = []
    skipped = 0
    for index, record in enumerate(sets):
        author = (owner or record.get("autor", "")).casefold()
        if author not in accounts:
            raise ValueError(
                "A set has no matching owner. Provide --users or --owner; no data was written."
            )
        cards = [
            c
            for c in record.get("karty", [])
            if c.get("tekst", "").strip() and c.get("odpowiedz", "").strip()
        ]
        if not cards:
            skipped += 1
            continue
        source_id = record.get("id")
        if not source_id:
            import hashlib

            source_id = hashlib.sha256(
                json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
        key = f"legacy:{accounts[author]}:{source_id}"
        if db.execute(
            "SELECT id FROM workspaces WHERE legacy_key=?", (key,)
        ).fetchone():
            skipped += 1
            continue
        imports.append((accounts[author], record, cards, key))
    summary = {
        "users": len(additions),
        "workspaces": len(imports),
        "activities": sum(len(x[2]) for x in imports),
        "skipped": skipped,
        "applied": apply,
    }
    if not apply:
        return summary
    with transaction() as db:
        for uid, name, password, created in additions:
            db.execute(
                "INSERT INTO users VALUES (?,?,?,0,?)", (uid, name, password, created)
            )
        for uid, record, cards, key in imports:
            wid, tid = uuid4().hex, uuid4().hex
            now = now_iso()
            db.execute(
                "INSERT INTO workspaces VALUES (?,?,?,?,?,?,?)",
                (
                    wid,
                    uid,
                    record.get("nazwa") or "Importowany zestaw",
                    "Zaimportowano z poprzedniej wersji.",
                    "blue",
                    now,
                    key,
                ),
            )
            db.execute(
                "INSERT INTO topics VALUES (?,?,?,?,?)",
                (
                    tid,
                    wid,
                    "Fiszki z poprzedniej wersji",
                    "Historia źródłowa zachowana w eksporcie.",
                    now,
                ),
            )
            db.execute(
                "INSERT INTO legacy_payloads VALUES (?,?,?)",
                (wid, json.dumps(record, ensure_ascii=False), now),
            )
            for card in cards:
                stats = card.get("statystyki") or {}
                aid = uuid4().hex
                db.execute(
                    "INSERT INTO activities VALUES (?,?,'flashcard','memory',?,?,'[]',1,0,?,?,?)",
                    (
                        aid,
                        tid,
                        card["tekst"],
                        card["odpowiedz"],
                        json.dumps(stats, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
    return summary


def init_app(app):
    @app.cli.command("import-legacy")
    @click.option(
        "--sets",
        "sets_path",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
    )
    @click.option("--users", "users_path", type=click.Path(exists=True, dir_okay=False))
    @click.option(
        "--owner", help="Explicitly assign all sets to this existing account."
    )
    @click.option("--apply", is_flag=True, help="Write import; default is dry-run.")
    def command(sets_path, users_path, owner, apply):
        try:
            click.echo(
                json.dumps(
                    import_legacy(sets_path, users_path, owner, apply),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except Exception as e:
            raise click.ClickException(str(e)) from e
