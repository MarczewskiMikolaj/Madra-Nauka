import json
import random
from uuid import uuid4
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from .auth import login_required
from .db import get_db, transaction
from .library import owned_topic, owned_workspace
from .services.learning import activities_for, choose_items, now_iso, save_progress

bp = Blueprint("study", __name__)


def owned_session(sid, db=None):
    row = (
        (db or get_db())
        .execute(
            "SELECT * FROM study_sessions WHERE id=? AND user_id=?", (sid, g.user["id"])
        )
        .fetchone()
    )
    if not row:
        abort(404)
    return row


def current_item(sid, db=None):
    return (
        (db or get_db())
        .execute(
            """SELECT i.* FROM session_items i LEFT JOIN reviews r ON r.item_id=i.id
                                    WHERE i.session_id=? AND r.id IS NULL ORDER BY i.position LIMIT 1""",
            (sid,),
        )
        .fetchone()
    )


@bp.post("/nauka/start")
@login_required
def start():
    wid = request.form.get("workspace_id") or None
    tid = request.form.get("topic_id") or None
    if tid:
        scope = owned_topic(tid)
        title = scope["name"]
    elif wid:
        scope = owned_workspace(wid)
        title = scope["name"]
    else:
        title = "Moja sesja na dziś"
    try:
        budget = int(request.form.get("budget", 10))
    except ValueError:
        abort(400)
    if budget not in (5, 10, 20):
        abort(400)
    with transaction() as db:
        active = db.execute(
            "SELECT id FROM study_sessions WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (g.user["id"],),
        ).fetchone()
        if active:
            sid = active["id"]
        else:
            items = choose_items(
                activities_for(g.user["id"], workspace_id=wid, topic_id=tid), budget
            )
            if not items:
                flash("Dodaj ćwiczenie w bibliotece, aby rozpocząć naukę.", "info")
                return redirect(url_for("library.index"))
            sid = uuid4().hex
            db.execute(
                "INSERT INTO study_sessions VALUES (?,?,?,?,'active',?,NULL)",
                (sid, g.user["id"], title, budget, now_iso()),
            )
            for pos, activity in enumerate(items):
                snapshot = {
                    key: activity[key]
                    for key in (
                        "kind",
                        "dimension",
                        "prompt",
                        "answer",
                        "minutes",
                        "topic_name",
                        "workspace_name",
                        "reason",
                    )
                }
                snapshot["options"] = json.loads(activity["options_json"])
                random.SystemRandom().shuffle(snapshot["options"])
                db.execute(
                    "INSERT INTO session_items VALUES (?,?,?,?,?,NULL,0,NULL)",
                    (
                        uuid4().hex,
                        sid,
                        activity["id"],
                        pos,
                        json.dumps(snapshot, ensure_ascii=False),
                    ),
                )
    return redirect(url_for("study.session_page", sid=sid))


@bp.get("/nauka/<sid>")
@login_required
def session_page(sid):
    study = owned_session(sid)
    rows = (
        get_db()
        .execute(
            """SELECT i.*,r.grade FROM session_items i LEFT JOIN reviews r ON r.item_id=i.id
                            WHERE i.session_id=? ORDER BY i.position""",
            (sid,),
        )
        .fetchall()
    )
    item = current_item(sid)
    if study["status"] != "active" or not item:
        reviewed = [r for r in rows if r["grade"] is not None]
        return render_template(
            "summary.html",
            study=study,
            items=reviewed,
            total=len(rows),
            success=sum(r["grade"] >= 2 for r in reviewed),
            nav="today",
        )
    activity = json.loads(item["snapshot_json"])
    last = (
        get_db()
        .execute(
            """SELECT r.id FROM reviews r JOIN session_items i ON i.id=r.item_id
                            WHERE i.session_id=? ORDER BY i.position DESC LIMIT 1""",
            (sid,),
        )
        .fetchone()
    )
    return render_template(
        "study.html",
        study=study,
        item=item,
        activity=activity,
        total=len(rows),
        last=last,
        nav="today",
    )


@bp.post("/nauka/<sid>/odpowiedz")
@login_required
def reveal(sid):
    with transaction() as db:
        study = owned_session(sid, db)
        item_id = request.form.get("item_id")
        existing = db.execute(
            "SELECT * FROM session_items WHERE id=? AND session_id=?", (item_id, sid)
        ).fetchone()
        if not existing:
            abort(404)
        item = current_item(sid, db)
        if existing["revealed"] or study["status"] != "active":
            return redirect(url_for("study.session_page", sid=sid))
        if not item or item["id"] != item_id:
            abort(409)
        activity = json.loads(item["snapshot_json"])
        response = request.form.get("response", "").strip()
        if len(response) > 10000:
            abort(400)
        objective = None
        if activity["kind"] == "quiz":
            if response not in activity["options"]:
                flash("Wybierz jedną odpowiedź.", "error")
                return redirect(url_for("study.session_page", sid=sid))
            objective = int(response == activity["answer"])
        elif activity["kind"] in ("open", "exercise", "cloze") and not response:
            flash("Zapisz swoją próbę odpowiedzi. Możesz wpisać „nie wiem”.", "error")
            return redirect(url_for("study.session_page", sid=sid))
        db.execute(
            "UPDATE session_items SET revealed=1,response=?,objective_correct=? WHERE id=?",
            (response, objective, item_id),
        )
    return redirect(url_for("study.session_page", sid=sid))


@bp.post("/nauka/<sid>/ocena")
@login_required
def grade(sid):
    item_id = request.form.get("item_id")
    with transaction() as db:
        study = owned_session(sid, db)
        item = db.execute(
            "SELECT * FROM session_items WHERE id=? AND session_id=?", (item_id, sid)
        ).fetchone()
        if not item:
            abort(404)
        if db.execute("SELECT id FROM reviews WHERE item_id=?", (item_id,)).fetchone():
            return redirect(url_for("study.session_page", sid=sid))
        current = current_item(sid, db)
        if (
            study["status"] != "active"
            or not current
            or current["id"] != item_id
            or not item["revealed"]
        ):
            abort(409)
        activity = json.loads(item["snapshot_json"])
        if activity["kind"] == "quiz":
            value = 2 if item["objective_correct"] else 0
        else:
            try:
                value = int(request.form.get("grade", ""))
            except ValueError:
                abort(400)
            if value not in range(4):
                abort(400)
        previous = save_progress(db, g.user["id"], item["activity_id"], value)
        db.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (
                uuid4().hex,
                item_id,
                g.user["id"],
                item["activity_id"],
                value,
                item["response"] or "",
                item["objective_correct"],
                previous,
                now_iso(),
            ),
        )
        if not current_item(sid, db):
            db.execute(
                "UPDATE study_sessions SET status='completed',finished_at=? WHERE id=?",
                (now_iso(), sid),
            )
    return redirect(url_for("study.session_page", sid=sid))


@bp.post("/nauka/<sid>/cofnij")
@login_required
def undo(sid):
    with transaction() as db:
        owned_session(sid, db)
        last = db.execute(
            """SELECT r.* FROM reviews r JOIN session_items i ON i.id=r.item_id
                           WHERE i.session_id=? ORDER BY i.position DESC LIMIT 1""",
            (sid,),
        ).fetchone()
        newest = db.execute(
            "SELECT id FROM reviews WHERE user_id=? ORDER BY created_at DESC LIMIT 1",
            (g.user["id"],),
        ).fetchone()
        other = db.execute(
            "SELECT id FROM study_sessions WHERE user_id=? AND status='active' AND id<>?",
            (g.user["id"], sid),
        ).fetchone()
        if not last or not newest or last["id"] != newest["id"] or other:
            abort(409)
        db.execute(
            "DELETE FROM progress WHERE user_id=? AND activity_id=?",
            (g.user["id"], last["activity_id"]),
        )
        if last["previous_progress_json"]:
            old = json.loads(last["previous_progress_json"])
            db.execute(
                "INSERT INTO progress VALUES (?,?,?,?,?,?,?,?)",
                tuple(
                    old[key]
                    for key in (
                        "user_id",
                        "activity_id",
                        "reviews",
                        "successes",
                        "last_grade",
                        "interval_days",
                        "due_date",
                        "updated_at",
                    )
                ),
            )
        db.execute("DELETE FROM reviews WHERE id=?", (last["id"],))
        db.execute(
            "UPDATE study_sessions SET status='active',finished_at=NULL WHERE id=?",
            (sid,),
        )
    flash("Ostatnia ocena cofnięta. Oceń odpowiedź ponownie.", "info")
    return redirect(url_for("study.session_page", sid=sid))


@bp.post("/nauka/<sid>/zakoncz")
@login_required
def end(sid):
    with transaction() as db:
        owned_session(sid, db)
        db.execute(
            "UPDATE study_sessions SET status='ended',finished_at=? WHERE id=? AND status='active'",
            (now_iso(), sid),
        )
    return redirect(url_for("study.session_page", sid=sid))
