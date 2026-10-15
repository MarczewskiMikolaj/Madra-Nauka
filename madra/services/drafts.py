"""Optimistic, owner-checked drafts kept separate from submitted answers."""

import json
from flask import abort, g
from .learning import now_iso


def item_draft(db, item_id):
    row = db.execute(
        "SELECT * FROM study_drafts WHERE item_id=?", (item_id,)
    ).fetchone()
    return (
        dict(row)
        if row
        else {
            "response": "",
            "response_mode": "text",
            "used_help": 0,
            "flagged": 0,
            "revision": 0,
        }
    )


def save_item_draft(db, sid, fields, *, enforce_revision=True):
    iid = fields.get("item_id", "")
    item = db.execute(
        "SELECT i.* FROM session_items i JOIN study_sessions s ON s.id=i.session_id WHERE i.id=? AND i.session_id=? AND s.user_id=? AND s.status='active'",
        (iid, sid, g.user["id"]),
    ).fetchone()
    if not item:
        abort(409)
    if (
        item["revealed"]
        or db.execute("SELECT 1 FROM reviews WHERE item_id=?", (iid,)).fetchone()
    ):
        abort(409)
    old = item_draft(db, iid)
    try:
        revision = int(fields.get("revision", old["revision"]))
    except (ValueError, TypeError):
        abort(400)
    if enforce_revision and revision != old["revision"]:
        abort(409)
    response = fields.get("response", "")
    mode = fields.get("response_mode", "text")
    activity = json.loads(item["snapshot_json"])
    if (
        not isinstance(response, str)
        or len(response) > 10000
        or mode not in ("text", "paper", "oral")
    ):
        abort(400)
    if activity["kind"] == "quiz" and response and response not in activity["options"]:
        abort(400)
    if activity["kind"] == "quiz" and mode != "text":
        abort(400)
    db.execute(
        """INSERT INTO study_drafts VALUES (?,?,?,?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET
        response=excluded.response,response_mode=excluded.response_mode,used_help=excluded.used_help,flagged=excluded.flagged,revision=excluded.revision,updated_at=excluded.updated_at""",
        (
            iid,
            response,
            mode,
            int(old["used_help"] or fields.get("used_help") == "1"),
            int(fields.get("flagged") == "1"),
            old["revision"] + 1,
            now_iso(),
        ),
    )
    return old["revision"] + 1
