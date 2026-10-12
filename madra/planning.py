import json
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
)
from .auth import login_required
from .db import get_db, transaction
from .library import owned_workspace, required_text
from .services.learning import (
    activities_for,
    choose_items,
    dimension_scores,
    now_iso,
    today_date,
)

bp = Blueprint("planning", __name__)


def goal_details(user_id):
    rows = (
        get_db()
        .execute(
            """SELECT g.*,w.name workspace_name,w.color FROM goals g
                            JOIN workspaces w ON w.id=g.workspace_id WHERE g.user_id=?
                            ORDER BY g.completed,g.target_date""",
            (user_id,),
        )
        .fetchall()
    )
    result = []
    for row in rows:
        goal = dict(row)
        activities = activities_for(user_id, workspace_id=row["workspace_id"])
        practiced = sum(bool(a["reviews"]) for a in activities)
        remaining = sum(a["minutes"] for a in activities if not a["reviews"])
        days = (date.fromisoformat(row["target_date"]) - today_date()).days
        goal.update(
            total=len(activities),
            practiced=practiced,
            coverage=round(practiced / len(activities) * 100) if activities else 0,
            days=days,
            estimated_remaining=remaining,
            feasible=remaining <= max(0, days + 1) * row["daily_minutes"],
        )
        result.append(goal)
    return result


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
    chosen = choose_items(activities, 10)
    active = (
        get_db()
        .execute(
            "SELECT * FROM study_sessions WHERE user_id=? AND status='active' ORDER BY created_at DESC LIMIT 1",
            (g.user["id"],),
        )
        .fetchone()
    )
    spaces = (
        get_db()
        .execute(
            "SELECT * FROM workspaces WHERE user_id=? ORDER BY created_at DESC",
            (g.user["id"],),
        )
        .fetchall()
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
        plan=chosen,
        active=active,
        spaces=spaces,
        due=sum(a["state"] == "due" for a in activities),
        new=sum(a["state"] == "new" for a in activities),
        date_label=f'{weekday}, {today_date().strftime("%d.%m.%Y")}',
        estimate=sum(a["minutes"] for a in chosen),
        goals=goal_details(g.user["id"])[:3],
        nav="today",
    )


@bp.get("/cele")
@login_required
def goals():
    spaces = (
        get_db()
        .execute(
            "SELECT * FROM workspaces WHERE user_id=? ORDER BY name", (g.user["id"],)
        )
        .fetchall()
    )
    return render_template(
        "goals.html", goals=goal_details(g.user["id"]), spaces=spaces, nav="goals"
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
        with transaction() as db:
            db.execute(
                "INSERT INTO goals VALUES (?,?,?,?,?,?,0,?)",
                (
                    uuid4().hex,
                    g.user["id"],
                    wid,
                    title,
                    target.isoformat(),
                    minutes,
                    now_iso(),
                ),
            )
        flash("Cel dodany. Możesz rozpocząć naukę w jego przedmiocie.", "success")
    except (ValueError, TypeError) as e:
        flash(
            (
                str(e)
                if str(e).startswith(("Nazwa", "Wybierz"))
                else "Wpisz poprawny termin i dzienny czas."
            ),
            "error",
        )
    return redirect(url_for("planning.goals"))


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
    return redirect(url_for("planning.goals"))


@bp.get("/postepy")
@login_required
def progress():
    activities = activities_for(g.user["id"])
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
    history = (
        get_db()
        .execute(
            """SELECT s.*,COUNT(r.id) answer_count FROM study_sessions s
                               LEFT JOIN session_items i ON i.session_id=s.id LEFT JOIN reviews r ON r.item_id=i.id
                               WHERE s.user_id=? GROUP BY s.id ORDER BY s.created_at DESC LIMIT 10""",
            (g.user["id"],),
        )
        .fetchall()
    )
    return render_template(
        "progress.html",
        scores=dimension_scores(activities),
        reviews=reviews,
        week=week,
        maximum=maximum,
        sessions=sessions,
        streak=streak,
        history=history,
        practiced=sum(bool(a["reviews"]) for a in activities),
        total=len(activities),
        nav="progress",
    )


@bp.get("/konto/eksport")
@login_required
def export():
    db = get_db()
    uid = g.user["id"]
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
        "legacy_payloads": (
            "SELECT l.* FROM legacy_payloads l JOIN workspaces w ON w.id=l.workspace_id WHERE w.user_id=?",
        ),
    }
    with transaction():
        result = {
            name: [dict(r) for r in db.execute(sql[0], (uid,)).fetchall()]
            for name, sql in tables.items()
        }
    result.update(version=2, exported_at=now_iso(), username=g.user["username"])
    return Response(
        json.dumps(result, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="madra-nauka-export.json"'
        },
    )
