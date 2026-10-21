import json
import tempfile
import zipfile
from datetime import date, timedelta, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
    Response,
    send_file,
)
from .auth import login_required
from .db import get_db, transaction, read_snapshot
from .library import owned_workspace, required_text
from .services.learning import (
    activities_for,
    dimension_scores,
    now_iso,
    today_date,
)

from .services.daily_plan import daily_budget, day_plan, week_plan, studied_minutes
from .services.goals import (
    enrich_goal,
    save_goal_settings,
    DAYS,
    settings_for,
)

bp = Blueprint("planning", __name__)


def goal_details(user_id):
    rows = (
        get_db()
        .execute(
            "SELECT g.*,w.name workspace_name,w.color FROM goals g JOIN workspaces w ON w.id=g.workspace_id WHERE g.user_id=? ORDER BY g.completed,g.target_date",
            (user_id,),
        )
        .fetchall()
    )
    return [enrich_goal(row) for row in rows]


@bp.get("/")
def landing():
    if g.user:
        return redirect(url_for("planning.today"))
    return render_template("landing.html")


@bp.get("/dashboard")
@bp.get("/dzisiaj")
@login_required
def today():
    activities = activities_for(g.user["id"])
    allowance = daily_budget(g.user["id"])
    spent = studied_minutes(g.user["id"])
    budget = request.args.get("budget", max(0, allowance - spent), type=int)
    if not 0 <= budget <= 180:
        abort(400)
    planned = day_plan(g.user["id"], budget)
    chosen = planned["items"]
    active = (
        get_db()
        .execute(
            "SELECT * FROM study_sessions WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (g.user["id"],),
        )
        .fetchone()
    )
    weekday = [
        "poniedziałek",
        "wtorek",
        "środa",
        "czwartek",
        "piątek",
        "sobota",
        "niedziela",
    ][today_date().weekday()]
    return render_template(
        "today.html",
        activities=activities,
        budget=budget,
        allowance=allowance,
        spent=spent,
        planned=planned,
        week_plan=week_plan(g.user["id"]),
        expired=get_db()
        .execute(
            "SELECT * FROM goals WHERE user_id=? AND completed=0 AND target_date<? ORDER BY target_date",
            (g.user["id"], today_date().isoformat()),
        )
        .fetchall(),
        weak=sum(bool(a["reviews"]) and a["last_grade"] < 2 for a in activities),
        paused=get_db()
        .execute(
            "SELECT s.* FROM study_sessions s JOIN session_settings x ON x.session_id=s.id WHERE s.user_id=? AND x.paused=1 ORDER BY s.created_at DESC LIMIT 5",
            (g.user["id"],),
        )
        .fetchall(),
        plan=chosen,
        active=active,
        date_label=f"{weekday}, {today_date().strftime('%d.%m.%Y')}",
        goal_data=goals_context(),
        progress_data=progress_context(activities),
        expanded=request.args.get("section", ""),
        nav="today",
    )


@bp.get("/cele")
@login_required
def goals():
    return redirect(url_for("planning.today", section="goals", _anchor="goals"))


def goals_context():
    spaces = (
        get_db()
        .execute(
            "SELECT * FROM workspaces w WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='workspace' AND cs.content_id=w.id) ORDER BY name",
            (g.user["id"],),
        )
        .fetchall()
    )
    return dict(
        goals=goal_details(g.user["id"]),
        spaces=spaces,
        all_topics=get_db()
        .execute(
            "SELECT t.* FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (w.id,t.id)) ORDER BY t.name",
            (g.user["id"],),
        )
        .fetchall(),
        days=DAYS,
        nav="goals",
    )


@bp.post("/cele/nowy")
@login_required
def add_goal():
    wid = request.form.get("workspace_id", "")
    owned_workspace(wid)
    try:
        title = required_text("title", "Nazwa celu", 150)
        target = date.fromisoformat(request.form.get("target_date", ""))
        minutes = int(request.form.get("daily_minutes", 20))
        if (
            target < today_date()
            or target > today_date() + timedelta(days=3650)
            or not 5 <= minutes <= 180
        ):
            raise ValueError(
                "Wybierz przyszły termin (do 10 lat) i 5–180 minut dziennie."
            )
        gid = uuid4().hex
        with transaction() as db:
            db.execute(
                "INSERT INTO goals VALUES (?,?,?,?,?,?,0,?)",
                (
                    gid,
                    g.user["id"],
                    wid,
                    title,
                    target.isoformat(),
                    minutes,
                    now_iso(),
                ),
            )
            save_goal_settings(db, {"id": gid, "workspace_id": wid})
        flash(
            "Cel i jego zakres zostały zapisane. Plan dnia uwzględni termin i dostępne dni.",
            "success",
        )
    except (ValueError, TypeError) as e:
        flash(
            (
                str(e)
                if str(e).startswith(("Nazwa", "Wybierz"))
                else "Wpisz poprawny termin i dzienny czas."
            ),
            "error",
        )
    return redirect(url_for("planning.today", section="goals", _anchor="goals"))


@bp.post("/cele/<gid>/status")
@login_required
def toggle_goal(gid):
    with transaction() as db:
        goal = db.execute(
            "SELECT * FROM goals WHERE id=? AND user_id=?", (gid, g.user["id"])
        ).fetchone()
        if not goal:
            abort(404)
        db.execute(
            "UPDATE goals SET completed=? WHERE id=?", (int(not goal["completed"]), gid)
        )
    return redirect(url_for("planning.today", section="goals", _anchor="goals"))


def owned_goal(gid):
    row = (
        get_db()
        .execute("SELECT * FROM goals WHERE id=? AND user_id=?", (gid, g.user["id"]))
        .fetchone()
    )
    if not row:
        abort(404)
    return row


@bp.route("/cele/<gid>/edytuj", methods=["GET", "POST"])
@login_required
def edit_goal(gid):
    goal = owned_goal(gid)
    if request.method == "POST":
        try:
            title = required_text("title", "Nazwa celu", 150)
            target = date.fromisoformat(request.form.get("target_date", ""))
            minutes = int(request.form.get("daily_minutes", ""))
            if (
                not today_date() <= target <= today_date() + timedelta(days=3650)
                or not 5 <= minutes <= 180
            ):
                raise ValueError()
            with transaction() as db:
                db.execute(
                    "UPDATE goals SET title=?,target_date=?,daily_minutes=? WHERE id=? AND user_id=?",
                    (title, target.isoformat(), minutes, gid, g.user["id"]),
                )
                save_goal_settings(db, goal)
            flash("Cel zaktualizowany. Rozpiska czasu została przeliczona.", "success")
            return redirect(url_for("planning.today", section="goals", _anchor="goals"))
        except (ValueError, TypeError) as error:
            flash(
                (
                    str(error)
                    if str(error).startswith(("Wybierz", "Ważność"))
                    else "Podaj nazwę celu, termin od dziś do 10 lat i 5–180 minut dziennie."
                ),
                "error",
            )
            return (
                render_template(
                    "goal_edit.html",
                    goal=goal,
                    settings=settings_for(goal),
                    topics=get_db()
                    .execute(
                        "SELECT t.*,COALESCE(gt.priority,1) priority,gt.topic_id IS NOT NULL selected FROM topics t LEFT JOIN goal_topics gt ON gt.topic_id=t.id AND gt.goal_id=? WHERE workspace_id=? ORDER BY name",
                        (gid, goal["workspace_id"]),
                    )
                    .fetchall(),
                    days=DAYS,
                    nav="goals",
                ),
                400,
            )
    return render_template(
        "goal_edit.html",
        goal=goal,
        settings=settings_for(goal),
        topics=get_db()
        .execute(
            "SELECT t.*,COALESCE(gt.priority,1) priority,gt.topic_id IS NOT NULL selected FROM topics t LEFT JOIN goal_topics gt ON gt.topic_id=t.id AND gt.goal_id=? WHERE workspace_id=? ORDER BY name",
            (gid, goal["workspace_id"]),
        )
        .fetchall(),
        days=DAYS,
        nav="goals",
    )


@bp.post("/cele/<gid>/usun")
@login_required
def delete_goal(gid):
    owned_goal(gid)
    with transaction() as db:
        db.execute("DELETE FROM goals WHERE id=? AND user_id=?", (gid, g.user["id"]))
    flash("Cel usunięty. Materiały i historia nauki pozostały zachowane.", "success")
    return redirect(url_for("planning.today", section="goals", _anchor="goals"))


@bp.get("/postepy")
@login_required
def progress():
    page = request.args.get("page", 1, type=int)
    if not 1 <= page <= 100000:
        abort(400)
    return redirect(
        url_for("planning.today", section="history", page=page, _anchor="history")
    )


def progress_context(activities):
    reviews = (
        get_db()
        .execute(
            "SELECT * FROM reviews WHERE user_id=? ORDER BY created_at DESC",
            (g.user["id"],),
        )
        .fetchall()
    )
    daily = {}
    tz = ZoneInfo(current_app.config["TIMEZONE"])
    for review in reviews:
        day = (
            datetime.fromisoformat(review["created_at"])
            .astimezone(tz)
            .date()
            .isoformat()
        )
        daily[day] = daily.get(day, 0) + 1
    week = [
        {
            "date": (today_date() - timedelta(days=i)).isoformat(),
            "label": ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"][
                (today_date() - timedelta(days=i)).weekday()
            ],
            "count": daily.get((today_date() - timedelta(days=i)).isoformat(), 0),
        }
        for i in range(6, -1, -1)
    ]
    maximum = max([d["count"] for d in week] + [1])
    sessions = (
        get_db()
        .execute(
            "SELECT COUNT(*) FROM study_sessions WHERE user_id=? AND status='completed'",
            (g.user["id"],),
        )
        .fetchone()[0]
    )
    streak = 0
    day = (
        today_date()
        if today_date().isoformat() in daily
        else today_date() - timedelta(days=1)
    )
    while day.isoformat() in daily:
        streak += 1
        day -= timedelta(days=1)
    page = request.args.get("page", 1, type=int)
    if not 1 <= page <= 100000:
        abort(400)
    history_total = (
        get_db()
        .execute("SELECT COUNT(*) FROM study_sessions WHERE user_id=?", (g.user["id"],))
        .fetchone()[0]
    )
    history = (
        get_db()
        .execute(
            """SELECT s.*,COUNT(CASE WHEN r.id IS NOT NULL OR e.item_id IS NOT NULL THEN i.id END) answer_count,COALESCE(x.paused,0) paused,COALESCE(x.mode,'regular') mode FROM study_sessions s
                               LEFT JOIN session_settings x ON x.session_id=s.id
                               LEFT JOIN session_items i ON i.session_id=s.id LEFT JOIN reviews r ON r.item_id=i.id LEFT JOIN exam_answers e ON e.item_id=i.id
                               WHERE s.user_id=? GROUP BY s.id ORDER BY s.created_at DESC LIMIT 10 OFFSET ?""",
            (g.user["id"], (page - 1) * 10),
        )
        .fetchall()
    )
    weak = [a for a in activities if a["reviews"] and a["last_grade"] < 2]
    topics = (
        get_db()
        .execute(
            "SELECT t.id,t.name,w.name workspace_name FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (w.id,t.id)) ORDER BY w.name,t.name",
            (g.user["id"],),
        )
        .fetchall()
    )
    topic_stats = []
    for t in topics:
        group = [a for a in activities if a["topic_id"] == t["id"]]
        topic_stats.append(
            {
                **dict(t),
                "total": len(group),
                "new": sum(not a["reviews"] for a in group),
                "weak": sum(bool(a["reviews"]) and a["last_grade"] < 2 for a in group),
            }
        )
    return dict(
        page=page,
        has_more=page * 10 < history_total,
        weak=weak,
        topic_stats=topic_stats,
        scores=dimension_scores(activities),
        reviews=reviews,
        week=week,
        maximum=maximum,
        sessions=sessions,
        streak=streak,
        history=history,
        practiced=sum(bool(a["reviews"]) for a in activities),
        total=len(activities),
        independent=get_db()
        .execute(
            "SELECT COUNT(*) FROM reviews r LEFT JOIN review_notes n ON n.review_id=r.id WHERE r.user_id=? AND COALESCE(n.used_help,0)=0 AND r.grade>=2",
            (g.user["id"],),
        )
        .fetchone()[0],
        assisted=get_db()
        .execute(
            "SELECT COUNT(*) FROM reviews r JOIN review_notes n ON n.review_id=r.id WHERE r.user_id=? AND n.used_help=1",
            (g.user["id"],),
        )
        .fetchone()[0],
        nav="progress",
    )


def export_payload(db, uid):
    tables = {
        "workspaces": ("SELECT * FROM workspaces WHERE user_id=?",),
        "topics": (
            "SELECT t.* FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
        ),
        "materials": (
            "SELECT m.* FROM materials m JOIN topics t ON t.id=m.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
        ),
        "activities": (
            "SELECT a.* FROM activities a JOIN topics t ON t.id=a.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
        ),
        "progress": ("SELECT * FROM progress WHERE user_id=?",),
        "goals": ("SELECT * FROM goals WHERE user_id=?",),
        "sessions": ("SELECT * FROM study_sessions WHERE user_id=?",),
        "session_items": (
            "SELECT i.* FROM session_items i JOIN study_sessions s ON s.id=i.session_id WHERE s.user_id=?",
        ),
        "reviews": ("SELECT * FROM reviews WHERE user_id=?",),
        "uploads": (
            "SELECT id,workspace_id,topic_id,filename,draft_json,created_at,imported_at FROM uploads WHERE user_id=?",
        ),
        "upload_activities": (
            "SELECT a.* FROM upload_activities a JOIN uploads u ON u.id=a.upload_id WHERE u.user_id=?",
        ),
        "upload_materials": (
            "SELECT m.* FROM upload_materials m JOIN uploads u ON u.id=m.upload_id WHERE u.user_id=?",
        ),
        "activity_support": (
            "SELECT x.* FROM activity_support x JOIN activities a ON a.id=x.activity_id JOIN topics t ON t.id=a.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
        ),
        "session_settings": (
            "SELECT x.* FROM session_settings x JOIN study_sessions s ON s.id=x.session_id WHERE s.user_id=?",
        ),
        "exam_answers": (
            "SELECT e.* FROM exam_answers e JOIN session_items i ON i.id=e.item_id JOIN study_sessions s ON s.id=i.session_id WHERE s.user_id=?",
        ),
        "review_notes": (
            "SELECT n.* FROM review_notes n JOIN reviews r ON r.id=n.review_id WHERE r.user_id=?",
        ),
        "goal_settings": (
            "SELECT x.* FROM goal_settings x JOIN goals g ON g.id=x.goal_id WHERE g.user_id=?",
        ),
        "goal_topics": (
            "SELECT x.* FROM goal_topics x JOIN goals g ON g.id=x.goal_id WHERE g.user_id=?",
        ),
        "activity_imports": ("SELECT * FROM activity_imports WHERE user_id=?",),
        "study_drafts": (
            "SELECT d.* FROM study_drafts d JOIN session_items i ON i.id=d.item_id JOIN study_sessions s ON s.id=i.session_id WHERE s.user_id=?",
        ),
        "topic_packages": ("SELECT * FROM topic_packages WHERE user_id=?",),
        "form_drafts": ("SELECT * FROM form_drafts WHERE user_id=?",),
        "daily_preferences": ("SELECT * FROM daily_preferences WHERE user_id=?",),
        "content_states": ("SELECT * FROM content_states WHERE user_id=?",),
        "reading_progress": ("SELECT * FROM reading_progress WHERE user_id=?",),
        "goal_requirements": (
            "SELECT r.* FROM goal_requirements r JOIN goals g ON g.id=r.goal_id WHERE g.user_id=?",
        ),
        "activity_images": (
            "SELECT i.* FROM activity_images i JOIN activities a ON a.id=i.activity_id JOIN topics t ON t.id=a.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
        ),
        "exam_options": (
            "SELECT e.* FROM exam_options e JOIN study_sessions s ON s.id=e.session_id WHERE s.user_id=?",
        ),
        "legacy_payloads": (
            "SELECT l.* FROM legacy_payloads l JOIN workspaces w ON w.id=l.workspace_id WHERE w.user_id=?",
        ),
    }
    result = {
        name: [dict(r) for r in db.execute(sql[0], (uid,)).fetchall()]
        for name, sql in tables.items()
    }
    import base64

    result["image_assets"] = [
        {
            "id": r["id"],
            "png_base64": base64.b64encode(r["png"]).decode(),
            "created_at": r["created_at"],
        }
        for r in db.execute("SELECT * FROM image_assets WHERE user_id=?", (uid,))
    ]
    result.update(
        version=2,
        exported_at=now_iso(),
        username=g.user["username"],
        email=g.user["email"],
    )
    return result


@bp.get("/konto/eksport")
@login_required
def export():
    with read_snapshot() as db:
        result = export_payload(db, g.user["id"])
    return Response(
        json.dumps(result, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="madra-nauka-export.json"'
        },
    )


@bp.get("/konto/archiwum")
@login_required
def archive_export():
    output = tempfile.SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b")
    try:
        with (
            read_snapshot() as db,
            zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive,
        ):
            result = export_payload(db, g.user["id"])
            result["archive_version"] = 1
            # Paths are generated from IDs, never supplied filenames.
            originals = []
            for source in db.execute(
                "SELECT id,filename,file_blob FROM uploads WHERE user_id=?",
                (g.user["id"],),
            ):
                filename = source["filename"].replace("\\", "/").rsplit("/", 1)[-1]
                filename = (
                    "".join(c for c in filename if c.isprintable()).strip(".")[:200]
                    or "material"
                )
                path = f"originals/{len(originals) + 1}/{filename}"
                archive.writestr(path, source["file_blob"])
                originals.append(
                    {
                        "upload_id": source["id"],
                        "filename": source["filename"],
                        "path": path,
                    }
                )
            result["originals"] = originals
            profile = db.execute(
                "SELECT avatar_png FROM user_profiles WHERE user_id=?", (g.user["id"],)
            ).fetchone()
            if profile and profile["avatar_png"]:
                archive.writestr("avatar.png", profile["avatar_png"])
            archive.writestr(
                "data.json", json.dumps(result, ensure_ascii=False, indent=2)
            )
        output.seek(0)
        response = send_file(
            output,
            mimetype="application/zip",
            as_attachment=True,
            download_name="madra-nauka-archive.zip",
        )
        response.headers["Cache-Control"] = "no-store"
        response.call_on_close(output.close)
        return response
    except BaseException:
        output.close()
        raise


@bp.post("/plan/czas")
@login_required
def save_daily_budget():
    try:
        minutes = int(request.form.get("budget", 20))
    except ValueError:
        abort(400)
    if not 5 <= minutes <= 180:
        abort(400)
    with transaction() as db:
        db.execute(
            "INSERT INTO daily_preferences VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET budget=excluded.budget",
            (g.user["id"], minutes),
        )
    return redirect(url_for("planning.today"))


@bp.post("/cele/<gid>/wymagania")
@login_required
def requirement(gid):
    goal = owned_goal(gid)
    with transaction() as db:
        rid = request.form.get("requirement_id")
        if rid:
            row = db.execute(
                "SELECT * FROM goal_requirements WHERE id=? AND goal_id=?", (rid, gid)
            ).fetchone()
            if not row:
                abort(404)
            if request.form.get("action") == "remove":
                db.execute("DELETE FROM goal_requirements WHERE id=?", (rid,))
            else:
                db.execute(
                    "UPDATE goal_requirements SET checked=? WHERE id=?",
                    (int(not row["checked"]), rid),
                )
        else:
            titles = [
                t.strip()
                for t in request.form.get("titles", "").splitlines()
                if t.strip()
            ]
            if not titles or len(titles) > 50 or any(len(t) > 200 for t in titles):
                abort(400)
            tid = request.form.get("topic_id") or None
            if (
                tid
                and owned_topic_for_requirement(tid)["workspace_id"]
                != goal["workspace_id"]
            ):
                abort(400)
            for title in titles:
                db.execute(
                    "INSERT INTO goal_requirements VALUES (?,?,?,?,0,?)",
                    (uuid4().hex, gid, title, tid, now_iso()),
                )
    return redirect(url_for("planning.today", section="goals", _anchor="goal-" + gid))


def owned_topic_for_requirement(tid):
    from .library import owned_topic

    return owned_topic(tid)


@bp.get("/plan/przypomnienie.ics")
@login_required
def reminder():
    # Download only: the user chooses whether to add it to their calendar.
    tomorrow = today_date() + timedelta(days=1)
    stamp = tomorrow.strftime("%Y%m%d") + "T180000"
    from urllib.parse import urljoin
    from flask import current_app

    base = current_app.config.get("PUBLIC_URL") or request.url_root
    link = urljoin(base.rstrip("/") + "/", "dzisiaj")
    data = "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Madra Nauka//Plan//PL",
            "BEGIN:VEVENT",
            "UID:" + uuid4().hex + "@madra-nauka",
            "DTSTAMP:" + datetime.now(ZoneInfo("UTC")).strftime("%Y%m%dT%H%M%SZ"),
            "DTSTART;TZID=Europe/Warsaw:" + stamp,
            "DURATION:PT" + str(daily_budget(g.user["id"])) + "M",
            "RRULE:FREQ=DAILY;COUNT=7",
            "SUMMARY:Krótka sesja nauki",
            "DESCRIPTION:Otwórz plan dnia: " + link,
            "URL:" + link,
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )
    return Response(
        data,
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="nauka.ics"'},
    )
