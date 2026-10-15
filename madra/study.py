import json
import random
import re
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
from .services.learning import activities_for, KINDS, now_iso, save_progress
from .services.goals import goal_activities, choose_learning
from .services.daily_plan import day_plan, daily_budget, balanced_exam
from .services.drafts import item_draft, save_item_draft

bp = Blueprint("study", __name__)
SKIPPED_RESPONSE = "Nie podjęto samodzielnej odpowiedzi."


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


def session_settings(sid, db=None):
    row = (
        (db or get_db())
        .execute("SELECT * FROM session_settings WHERE session_id=?", (sid,))
        .fetchone()
    )
    return dict(row) if row else {"mode": "regular", "scope_json": "{}", "paused": 0}


def current_item(sid, db=None):
    db = db or get_db()
    if session_settings(sid, db)["mode"] == "exam":
        return db.execute(
            "SELECT i.* FROM session_items i LEFT JOIN exam_answers e ON e.item_id=i.id WHERE i.session_id=? AND e.item_id IS NULL ORDER BY position LIMIT 1",
            (sid,),
        ).fetchone()
    return db.execute(
        "SELECT i.* FROM session_items i LEFT JOIN reviews r ON r.item_id=i.id WHERE i.session_id=? AND r.id IS NULL ORDER BY i.position LIMIT 1",
        (sid,),
    ).fetchone()


@bp.get("/nauka/przygotuj")
@login_required
def prepare():
    tid = request.args.get("topic_id") or None
    wid = request.args.get("workspace_id") or None
    goal_id = request.args.get("goal_id") or None
    title = (
        owned_topic(tid)["name"]
        if tid
        else owned_workspace(wid)["name"] if wid else "Moja nauka"
    )
    if goal_id:
        from .planning import owned_goal

        title = owned_goal(goal_id)["title"]
    return render_template(
        "study_prepare.html",
        title=title,
        mode=request.args.get("mode", "regular"),
        scope={
            "global_scope": (
                "1"
                if request.args.get("all") == "1"
                or request.args.get("mode") in ("difficult", "exam")
                else "0"
            ),
            "topic_id": tid or "",
            "workspace_id": wid or "",
            "goal_id": goal_id or "",
        },
        budget=daily_budget(g.user["id"]),
        goals=get_db()
        .execute(
            "SELECT id,title FROM goals WHERE user_id=? AND completed=0 ORDER BY target_date",
            (g.user["id"],),
        )
        .fetchall(),
        nav="today",
    )


@bp.post("/nauka/start")
@login_required
def start():
    wid = request.form.get("workspace_id") or None
    tid = request.form.get("topic_id") or None
    goal_id = request.form.get("goal_id") or None
    activity_id = request.form.get("activity_id") or None
    mode = request.form.get("mode", "regular")
    if mode not in ("regular", "difficult", "exam"):
        abort(400)
    if activity_id and (mode != "regular" or goal_id):
        abort(400)
    try:
        budget = int(request.form.get("budget", daily_budget(g.user["id"])))
    except ValueError:
        abort(400)
    if not 1 <= budget <= 180:
        abort(400)
    kinds = request.form.getlist("kinds")
    if any(k not in KINDS for k in kinds):
        abort(400)
    if tid:
        topic = owned_topic(tid)
        if wid and wid != topic["workspace_id"]:
            abort(400)
        title = topic["name"]
    elif wid:
        title = owned_workspace(wid)["name"]
    else:
        title = "Moja sesja na dziś"
    if goal_id:
        from .planning import owned_goal

        goal = owned_goal(goal_id)
        if tid or wid:
            abort(400)
        title = goal["title"]
    if not tid and not wid and not goal_id:
        title = (
            "Plan dnia"
            if mode == "regular" and request.form.get("global_scope") != "1"
            else "Wszystkie przedmioty"
        )
    if mode == "exam":
        title = "Sprawdzian: " + title
    elif mode == "difficult":
        title = "Trudności: " + title
    try:
        exam_count = int(request.form.get("exam_count", 0) or 0)
        timer = int(request.form.get("timer_minutes", 0) or 0)
    except ValueError:
        abort(400)
    if not 0 <= exam_count <= 30 or not 0 <= timer <= 180:
        abort(400)
    scope = {
        "workspace_id": wid,
        "topic_id": tid,
        "goal_id": goal_id,
        "kinds": sorted(set(kinds)),
    }
    if activity_id:
        scope["activity_id"] = activity_id
    if not wid and not tid and not goal_id:
        scope["selection"] = (
            "day"
            if mode == "regular" and request.form.get("global_scope") != "1"
            else "all"
        )
    if mode == "exam" and exam_count:
        scope.update(exam_count=exam_count, timer_minutes=timer)
    if request.form.get("repeat_errors") == "1":
        scope["repeat_errors"] = True
    with transaction() as db:
        single = None
        if activity_id:
            single = next(
                (
                    a
                    for a in activities_for(
                        g.user["id"], workspace_id=wid, topic_id=tid
                    )
                    if a["id"] == activity_id
                ),
                None,
            )
            if not single:
                abort(404)
        active = db.execute(
            "SELECT * FROM study_sessions WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (g.user["id"],),
        ).fetchone()
        if active:
            settings = session_settings(active["id"], db)
            same = (
                settings["mode"] == mode and json.loads(settings["scope_json"]) == scope
            )
            # Historical sessions have no persisted scope; global resume stays available.
            if same or (
                settings["scope_json"] == "{}"
                and not tid
                and not wid
                and not goal_id
                and mode == "regular"
            ):
                return redirect(url_for("study.session_page", sid=active["id"]))
            if request.form.get("switch") != "1":
                return (
                    render_template(
                        "session_conflict.html",
                        active=active,
                        title=title,
                        fields={
                            **scope,
                            "mode": mode,
                            "budget": budget,
                            "repeat_errors": "1" if scope.get("repeat_errors") else "0",
                            "global_scope": request.form.get("global_scope", "0"),
                        },
                        nav="today",
                    ),
                    409,
                )
            if request.form.get("active_id") != active["id"]:
                abort(409)
        pool = (
            goal_activities(goal)
            if goal_id
            else activities_for(g.user["id"], workspace_id=wid, topic_id=tid)
        )
        if kinds:
            pool = [a for a in pool if a["kind"] in kinds]
        is_daily = (
            not tid
            and not wid
            and not goal_id
            and request.form.get("global_scope") != "1"
            and mode == "regular"
            and not activity_id
        )
        items = (
            balanced_exam(pool, exam_count)
            if mode == "exam" and exam_count
            else (
                day_plan(g.user["id"], budget)["items"]
                if is_daily and not kinds
                else choose_learning(pool, budget, mode)
            )
        )
        if is_daily and kinds:
            items = day_plan(g.user["id"], budget, kinds=kinds)["items"]
        if single:
            items = [single]
        if not items:
            flash(
                "Brak ćwiczeń dla wybranego zakresu i trybu. Dodaj ćwiczenia lub zmień wybór.",
                "info",
            )
            return redirect(
                url_for("library.topic", tid=tid) if tid else url_for("library.index")
            )
        if active:
            db.execute(
                "UPDATE study_sessions SET status='ended',finished_at=NULL WHERE id=?",
                (active["id"],),
            )
            db.execute(
                "INSERT INTO session_settings (session_id,paused) VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET paused=1",
                (active["id"],),
            )
        sid = uuid4().hex
        db.execute(
            "INSERT INTO study_sessions VALUES (?,?,?,?,'active',?,NULL)",
            (sid, g.user["id"], title, budget, now_iso()),
        )
        db.execute(
            "INSERT INTO session_settings (session_id,mode,scope_json) VALUES (?,?,?)",
            (sid, mode, json.dumps(scope)),
        )
        if mode == "exam" and exam_count:
            db.execute(
                "INSERT INTO exam_options VALUES (?,?,?,?)", (sid, 1, timer, exam_count)
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
                    "topic_id",
                    "upload_id",
                    "source_label",
                    "material_id",
                    "source_chapter",
                    "explanation",
                    "rubric",
                    "image_id",
                )
            }
            label = activity.get("source_label") or ""
            page = re.search(r"(?i)(?:strona|strony|str\.|s\.|page)\s*(\d{1,3})", label)
            snapshot["source_page"] = (
                int(page.group(1)) if page and 1 <= int(page.group(1)) <= 100 else 0
            )
            snapshot["hints"] = json.loads(activity.get("hints_json") or "[]")
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


@bp.post("/nauka/<sid>/wznow")
@login_required
def resume(sid):
    with transaction() as db:
        study = owned_session(sid, db)
        if not session_settings(sid, db)["paused"]:
            abort(409)
        active = db.execute(
            "SELECT * FROM study_sessions WHERE user_id=? AND status='active' AND id<>?",
            (g.user["id"], sid),
        ).fetchone()
        if active:
            if (
                request.form.get("switch") != "1"
                or request.form.get("active_id") != active["id"]
            ):
                return (
                    render_template(
                        "session_conflict.html",
                        active=active,
                        title=study["title"],
                        resume_id=sid,
                        fields={},
                        nav="today",
                    ),
                    409,
                )
            db.execute(
                "UPDATE study_sessions SET status='ended',finished_at=NULL WHERE id=?",
                (active["id"],),
            )
            db.execute(
                "UPDATE session_settings SET paused=1 WHERE session_id=?",
                (active["id"],),
            )
        db.execute(
            "UPDATE study_sessions SET status='active',finished_at=NULL WHERE id=?",
            (sid,),
        )
        db.execute("UPDATE session_settings SET paused=0 WHERE session_id=?", (sid,))
    return redirect(url_for("study.session_page", sid=sid))


@bp.post("/nauka/<sid>/przerwa")
@login_required
def pause(sid):
    with transaction() as db:
        study = owned_session(sid, db)
        if study["status"] == "active":
            if request.form.get("item_id"):
                save_item_draft(db, sid, request.form)
            db.execute(
                "UPDATE study_sessions SET status='ended',finished_at=NULL WHERE id=?",
                (sid,),
            )
            db.execute(
                "INSERT INTO session_settings (session_id,paused) VALUES (?,1) ON CONFLICT(session_id) DO UPDATE SET paused=1",
                (sid,),
            )
    return redirect(url_for("planning.today"))


def review_rows(sid):
    rows = (
        get_db()
        .execute(
            "SELECT i.*,r.grade,r.id review_id,n.used_help,n.reason error_reason,COALESCE(d.flagged,0) flagged,e.response exam_response,e.objective_correct exam_correct FROM session_items i LEFT JOIN reviews r ON r.item_id=i.id LEFT JOIN review_notes n ON n.review_id=r.id LEFT JOIN exam_answers e ON e.item_id=i.id LEFT JOIN study_drafts d ON d.item_id=i.id WHERE i.session_id=? ORDER BY position",
            (sid,),
        )
        .fetchall()
    )
    return [{**dict(r), "activity": json.loads(r["snapshot_json"])} for r in rows]


@bp.get("/nauka/<sid>")
@login_required
def session_page(sid):
    study = owned_session(sid)
    settings = session_settings(sid)
    rows = review_rows(sid)
    item = current_item(sid)
    feedback = None
    if request.args.get("feedback") and settings["mode"] != "exam":
        feedback = (
            get_db()
            .execute(
                "SELECT i.* FROM session_items i JOIN reviews r ON r.item_id=i.id "
                "WHERE i.session_id=? AND i.id=? AND i.revealed=1",
                (sid, request.args["feedback"]),
            )
            .fetchone()
        )
        if not feedback or json.loads(feedback["snapshot_json"])["kind"] != "quiz":
            abort(404)
        item = feedback
    exam_options = (
        get_db()
        .execute("SELECT * FROM exam_options WHERE session_id=?", (sid,))
        .fetchone()
    )
    if settings["mode"] == "exam" and study["status"] == "active" and exam_options:
        requested = request.args.get("item")
        if requested:
            item = (
                get_db()
                .execute(
                    "SELECT * FROM session_items WHERE id=? AND session_id=?",
                    (requested, sid),
                )
                .fetchone()
            )
            if not item:
                abort(404)
        elif not item:
            item = (
                get_db()
                .execute(
                    "SELECT * FROM session_items WHERE session_id=? ORDER BY position LIMIT 1",
                    (sid,),
                )
                .fetchone()
            )
    if settings["paused"]:
        return render_template(
            "session_paused.html",
            study=study,
            settings=settings,
            total=len(rows),
            nav="today",
        )
    if (study["status"] != "active" or not item) and not feedback:
        exam = settings["mode"] == "exam"
        reviewed = [r for r in rows if r["grade"] is not None]
        submitted = (
            [r for r in rows if r["exam_response"] is not None] if exam else reviewed
        )
        topics = {}
        for r in submitted:
            name = r["activity"].get("topic_name", "Temat")
            stat = topics.setdefault(
                name,
                {"total": 0, "correct": 0, "objective": 0, "self": 0, "pending": 0},
            )
            stat["total"] += 1
            if r["grade"] is None:
                stat["pending"] += 1
            elif r["activity"]["kind"] == "quiz":
                stat["objective"] += 1
                stat["correct"] += int(r["grade"] >= 2)
            else:
                stat["self"] += 1
        study_scope = {
            k: v
            for k, v in json.loads(settings["scope_json"]).items()
            if k in ("topic_id", "workspace_id", "goal_id") and v
        }
        if not study_scope:
            study_scope = {"all": 1}
        return render_template(
            "summary.html",
            study=study,
            settings=settings,
            items=submitted,
            reviewed=reviewed,
            total=len(rows),
            success=sum(r["grade"] >= 2 for r in reviewed),
            topic_results=topics,
            study_scope=study_scope,
            nav="today",
        )
    activity = json.loads(item["snapshot_json"])
    last = (
        get_db()
        .execute(
            "SELECT r.id FROM reviews r JOIN session_items i ON i.id=r.item_id WHERE i.session_id=? ORDER BY position DESC LIMIT 1",
            (sid,),
        )
        .fetchone()
    )
    return render_template(
        "exam.html" if settings["mode"] == "exam" else "study.html",
        study=study,
        item=item,
        activity=activity,
        total=len(rows),
        last=last,
        settings=settings,
        feedback=bool(feedback),
        skipped=(item["response"] or "").startswith(SKIPPED_RESPONSE),
        draft=item_draft(get_db(), item["id"]),
        exam_options=exam_options,
        exam_items=rows,
        exam_response=get_db()
        .execute("SELECT response FROM exam_answers WHERE item_id=?", (item["id"],))
        .fetchone(),
        nav="today",
    )


@bp.post("/nauka/<sid>/szkic")
@login_required
def save_draft(sid):
    with transaction() as db:
        owned_session(sid, db)
        if session_settings(sid, db)["paused"]:
            abort(409)
        revision = save_item_draft(db, sid, request.form)
    return {"revision": revision}


def record_review(
    db, item, uid, value, response, objective, used_help=False, reason=""
):
    previous = save_progress(db, uid, item["activity_id"], value)
    rid = uuid4().hex
    db.execute(
        "INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,NULL)",
        (
            rid,
            item["id"],
            uid,
            item["activity_id"],
            value,
            response,
            objective,
            previous,
            now_iso(),
        ),
    )
    db.execute("INSERT INTO review_notes VALUES (?,?,?)", (rid, int(used_help), reason))


def finish_review(db, sid, item, value, *, is_exam=False):
    repeat = json.loads(session_settings(sid, db)["scope_json"]).get("repeat_errors")
    if not is_exam and repeat and value == 0:
        remaining = db.execute(
            "SELECT COUNT(*) FROM session_items i LEFT JOIN reviews r ON r.item_id=i.id WHERE i.session_id=? AND r.id IS NULL",
            (sid,),
        ).fetchone()[0]
        occurrences = db.execute(
            "SELECT COUNT(*) FROM session_items WHERE session_id=? AND activity_id=?",
            (sid, item["activity_id"]),
        ).fetchone()[0]
        if remaining >= 2 and occurrences < 2:
            position = db.execute(
                "SELECT MAX(position)+1 FROM session_items WHERE session_id=?",
                (sid,),
            ).fetchone()[0]
            snapshot = json.loads(item["snapshot_json"])
            snapshot["reason"] = "Ponowna próba po innych pytaniach"
            db.execute(
                "INSERT INTO session_items VALUES (?,?,?,?,?,NULL,0,NULL)",
                (
                    uuid4().hex,
                    sid,
                    item["activity_id"],
                    position,
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )
    if not current_item(sid, db):
        db.execute(
            "UPDATE study_sessions SET status='completed',finished_at=? WHERE id=?",
            (now_iso(), sid),
        )


@bp.post("/nauka/<sid>/egzamin-odpowiedz")
@login_required
def exam_answer(sid):
    with transaction() as db:
        study = owned_session(sid, db)
        if session_settings(sid, db)["mode"] != "exam":
            abort(409)
        iid = request.form.get("item_id", "")
        item = db.execute(
            "SELECT * FROM session_items WHERE id=? AND session_id=?", (iid, sid)
        ).fetchone()
        if not item:
            abort(404)
        manual = db.execute(
            "SELECT 1 FROM exam_options WHERE session_id=?", (sid,)
        ).fetchone()
        if study["status"] != "active" or session_settings(sid, db)["paused"]:
            abort(409)
        current = current_item(sid, db)
        if not manual:
            if db.execute(
                "SELECT 1 FROM exam_answers WHERE item_id=?", (iid,)
            ).fetchone():
                return redirect(url_for("study.session_page", sid=sid))
            if not current or current["id"] != iid:
                abort(409)
        if manual and request.form.get("go_to"):
            target = request.form["go_to"]
            if not db.execute(
                "SELECT 1 FROM session_items WHERE id=? AND session_id=?", (target, sid)
            ).fetchone():
                abort(404)
            save_item_draft(db, sid, request.form)
            return redirect(url_for("study.session_page", sid=sid, item=target))
        activity = json.loads(item["snapshot_json"])
        response = request.form.get("response", "").strip()
        if (
            request.form.get("response_mode") in ("paper", "oral")
            and activity["kind"] != "quiz"
        ):
            response = response or (
                "Rozwiązano na kartce"
                if request.form["response_mode"] == "paper"
                else "Odpowiedź ustna"
            )
        if (
            not response
            or len(response) > 10000
            or (activity["kind"] == "quiz" and response not in activity["options"])
        ):
            abort(400)
        objective = (
            int(response == activity["answer"]) if activity["kind"] == "quiz" else None
        )
        db.execute(
            "INSERT INTO exam_answers VALUES (?,?,?,?) ON CONFLICT(item_id) DO UPDATE SET response=excluded.response,objective_correct=excluded.objective_correct,submitted_at=excluded.submitted_at",
            (iid, response, objective, now_iso()),
        )
        if manual:
            save_item_draft(db, sid, request.form)
        elif not current_item(sid, db):
            finish_exam(db, study)
    return redirect(url_for("study.session_page", sid=sid))


def finish_exam(db, study):
    rows = db.execute(
        "SELECT i.*,e.response exam_response,e.objective_correct exam_correct FROM session_items i JOIN exam_answers e ON e.item_id=i.id WHERE i.session_id=? ORDER BY position",
        (study["id"],),
    ).fetchall()
    for item in rows:
        if (
            item["exam_correct"] is not None
            and not db.execute(
                "SELECT 1 FROM reviews WHERE item_id=?", (item["id"],)
            ).fetchone()
        ):
            record_review(
                db,
                item,
                study["user_id"],
                2 if item["exam_correct"] else 0,
                item["exam_response"],
                item["exam_correct"],
            )
    db.execute(
        "UPDATE study_sessions SET status='completed',finished_at=? WHERE id=?",
        (now_iso(), study["id"]),
    )


@bp.post("/nauka/<sid>/odpowiedz")
@login_required
def reveal(sid):
    with transaction() as db:
        study = owned_session(sid, db)
        if session_settings(sid, db)["mode"] == "exam":
            abort(409)
        item_id = request.form.get("item_id")
        existing = db.execute(
            "SELECT * FROM session_items WHERE id=? AND session_id=?", (item_id, sid)
        ).fetchone()
        if not existing:
            abort(404)
        item = current_item(sid, db)
        if existing["revealed"] or study["status"] != "active":
            if (
                json.loads(existing["snapshot_json"])["kind"] == "quiz"
                and db.execute(
                    "SELECT 1 FROM reviews WHERE item_id=?", (item_id,)
                ).fetchone()
            ):
                return redirect(
                    url_for("study.session_page", sid=sid, feedback=item_id)
                )
            return redirect(url_for("study.session_page", sid=sid))
        if not item or item["id"] != item_id:
            abort(409)
        activity = json.loads(item["snapshot_json"])
        response = request.form.get("response", "").strip()
        if len(response) > 10000:
            abort(400)
        objective = None
        skipped = request.form.get("skip") == "1" and activity["kind"] not in (
            "quiz",
            "flashcard",
        )
        if activity["kind"] == "quiz":
            if response not in activity["options"]:
                flash("Wybierz jedną odpowiedź.", "error")
                return redirect(url_for("study.session_page", sid=sid))
            objective = int(response == activity["answer"])
        elif skipped:
            response = SKIPPED_RESPONSE + (
                "\n\nRozpoczęta odpowiedź: " + response if response else ""
            )
        elif request.form.get("response_mode") in ("paper", "oral"):
            response = response or (
                "Rozwiązano na kartce"
                if request.form["response_mode"] == "paper"
                else "Odpowiedź ustna"
            )
        elif activity["kind"] in ("open", "exercise", "cloze") and not response:
            flash("Zapisz swoją próbę odpowiedzi. Możesz wpisać „nie wiem”.", "error")
            return redirect(url_for("study.session_page", sid=sid))
        if "revision" in request.form or skipped:
            fields = request.form.copy()
            if skipped:
                fields["used_help"] = "1"
            save_item_draft(db, sid, fields)
        db.execute(
            "UPDATE session_items SET revealed=1,response=?,objective_correct=? WHERE id=?",
            (response, objective, item_id),
        )
        if activity["kind"] == "quiz":
            value = 2 if objective else 0
            record_review(
                db,
                item,
                g.user["id"],
                value,
                response,
                objective,
                bool(item_draft(db, item_id)["used_help"]),
            )
            finish_review(db, sid, item, value)
            return redirect(url_for("study.session_page", sid=sid, feedback=item_id))
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
        is_exam = session_settings(sid, db)["mode"] == "exam"
        exam_row = (
            db.execute(
                "SELECT * FROM exam_answers WHERE item_id=?", (item_id,)
            ).fetchone()
            if is_exam
            else None
        )
        if is_exam:
            if study["status"] != "completed" or not exam_row:
                abort(409)
        elif (
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
            if not is_exam and (item["response"] or "").startswith(SKIPPED_RESPONSE):
                value = 0
        reason = request.form.get("error_reason", "")
        if reason not in (
            "",
            "knowledge",
            "reasoning",
            "calculation",
            "attention",
            "other",
        ):
            abort(400)
        record_review(
            db,
            item,
            g.user["id"],
            value,
            exam_row["response"] if is_exam else item["response"] or "",
            exam_row["objective_correct"] if is_exam else item["objective_correct"],
            request.form.get("used_help") == "1"
            or bool(item_draft(db, item_id)["used_help"]),
            reason,
        )
        finish_review(db, sid, item, value, is_exam=is_exam)
    return redirect(url_for("study.session_page", sid=sid))


@bp.post("/nauka/<sid>/cofnij")
@login_required
def undo(sid):
    expected = request.form.get("review_id", "")
    if not expected:
        abort(400)
    with transaction() as db:
        owned_session(sid, db)
        if session_settings(sid, db)["mode"] == "exam":
            abort(409)
        # Retrying a correction must not remove the preceding answer as well.
        if not db.execute(
            "SELECT r.id FROM reviews r JOIN session_items i ON i.id=r.item_id WHERE r.id=? AND i.session_id=?",
            (expected, sid),
        ).fetchone():
            return redirect(url_for("study.session_page", sid=sid))
        last = db.execute(
            """SELECT r.* FROM reviews r JOIN session_items i ON i.id=r.item_id
                           WHERE i.session_id=? ORDER BY i.position DESC LIMIT 1""",
            (sid,),
        ).fetchone()
        newest = db.execute(
            "SELECT id FROM reviews WHERE user_id=? ORDER BY rowid DESC LIMIT 1",
            (g.user["id"],),
        ).fetchone()
        other = db.execute(
            "SELECT id FROM study_sessions WHERE user_id=? AND status='active' AND id<>?",
            (g.user["id"], sid),
        ).fetchone()
        if (
            not last
            or last["id"] != expected
            or not newest
            or last["id"] != newest["id"]
            or other
        ):
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
            """DELETE FROM session_items WHERE session_id=? AND activity_id=?
            AND position>(SELECT position FROM session_items WHERE id=?)
            AND json_extract(snapshot_json,'$.reason')='Ponowna próba po innych pytaniach'
            AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.item_id=session_items.id)""",
            (sid, last["activity_id"], last["item_id"]),
        )
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
        study = owned_session(sid, db)
        if session_settings(sid, db)["mode"] == "exam" and study["status"] == "active":
            if request.form.get("item_id"):
                save_item_draft(db, sid, request.form)
            finish_exam(db, study)
            return redirect(url_for("study.session_page", sid=sid))
        db.execute(
            "UPDATE study_sessions SET status='ended',finished_at=? WHERE id=? AND status='active'",
            (now_iso(), sid),
        )
    return redirect(url_for("study.session_page", sid=sid))


@bp.get("/nauka/<sid>/zakoncz")
@login_required
def end_confirmation(sid):
    study = owned_session(sid)
    settings = session_settings(sid)
    if study["status"] != "active" or settings["mode"] != "exam":
        return redirect(url_for("study.session_page", sid=sid))
    rows = review_rows(sid)
    return render_template(
        "exam_finish.html",
        study=study,
        total=len(rows),
        answered=sum(r["exam_response"] is not None for r in rows),
        flagged=sum(bool(r["flagged"]) for r in rows),
        nav="today",
    )
