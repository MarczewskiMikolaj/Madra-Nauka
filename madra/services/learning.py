import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import current_app
from ..db import get_db

KINDS = {
    "flashcard": "Fiszka",
    "open": "Pytanie otwarte",
    "quiz": "Quiz",
    "exercise": "Zadanie",
    "cloze": "Luka",
}
DIMENSIONS = {
    "memory": "Zapamiętanie",
    "understanding": "Zrozumienie",
    "application": "Zastosowanie",
}
KIND_DIMENSION = {
    "flashcard": "memory",
    "cloze": "memory",
    "open": "understanding",
    "quiz": "understanding",
    "exercise": "application",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today_date():
    return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).date()


def activities_for(user_id, workspace_id=None, topic_id=None):
    sql = """SELECT a.*,t.name topic_name,w.name workspace_name,w.color,w.id workspace_id,
             p.reviews,p.last_grade,p.due_date,p.interval_days, u.id upload_id,u.filename source_filename, ua.source_label
             FROM activities a JOIN topics t ON t.id=a.topic_id
             JOIN workspaces w ON w.id=t.workspace_id
             LEFT JOIN progress p ON p.activity_id=a.id AND p.user_id=?
             LEFT JOIN upload_activities ua ON ua.activity_id=a.id
             LEFT JOIN uploads u ON u.id=ua.upload_id
             WHERE w.user_id=? AND a.archived=0"""
    args = [user_id, user_id]
    if workspace_id:
        sql += " AND w.id=?"
        args.append(workspace_id)
    if topic_id:
        sql += " AND t.id=?"
        args.append(topic_id)
    sql += " ORDER BY a.created_at,a.id"
    result = []
    today = today_date().isoformat()
    for row in get_db().execute(sql, args).fetchall():
        item = dict(row)
        item["state"] = (
            "new"
            if not item["reviews"]
            else ("due" if item["due_date"] <= today else "scheduled")
        )
        item["reason"] = {
            "new": "Nowe ćwiczenie",
            "due": "Czas na powtórkę",
            "scheduled": "Dodatkowe utrwalenie",
        }[item["state"]]
        result.append(item)
    return sorted(
        result,
        key=lambda a: (
            {"due": 0, "new": 1, "scheduled": 2}[a["state"]],
            a["due_date"] or "",
            a["created_at"],
            a["id"],
        ),
    )


def choose_items(activities, budget):
    pending = [a for a in activities if a["state"] != "scheduled"]
    pool = pending or activities
    chosen, elapsed = [], 0
    for activity in pool:
        if elapsed + activity["minutes"] <= budget and len(chosen) < 30:
            chosen.append(activity)
            elapsed += activity["minutes"]
    return chosen or pool[:1]


def next_interval(previous, grade):
    if grade == 0:
        return 1
    if grade == 1:
        return max(1, min(7, round(previous * 1.2)))
    if grade == 2:
        return min(90, max(3, round(previous * 2)))
    return min(90, max(5, round(previous * 2.8)))


def save_progress(db, user_id, activity_id, grade):
    row = db.execute(
        "SELECT * FROM progress WHERE user_id=? AND activity_id=?",
        (user_id, activity_id),
    ).fetchone()
    previous = dict(row) if row else None
    interval = next_interval(row["interval_days"] if row else 0, grade)
    db.execute(
        """INSERT INTO progress VALUES (?,?,?,?,?,?,?,?)
                  ON CONFLICT(user_id,activity_id) DO UPDATE SET
                  reviews=excluded.reviews,successes=excluded.successes,last_grade=excluded.last_grade,
                  interval_days=excluded.interval_days,due_date=excluded.due_date,updated_at=excluded.updated_at""",
        (
            user_id,
            activity_id,
            (row["reviews"] if row else 0) + 1,
            (row["successes"] if row else 0) + int(grade >= 2),
            grade,
            interval,
            (today_date() + timedelta(days=interval)).isoformat(),
            now_iso(),
        ),
    )
    return json.dumps(previous) if previous else None


def dimension_scores(activities):
    result = []
    for key, label in DIMENSIONS.items():
        group = [a for a in activities if a["dimension"] == key]
        practiced = [a for a in group if a["reviews"]]
        score = (
            round(
                sum(min(a["last_grade"], 2) / 2 for a in practiced) / len(group) * 100
            )
            if group
            else 0
        )
        result.append(
            {
                "key": key,
                "label": label,
                "score": score,
                "total": len(group),
                "practiced": len(practiced),
            }
        )
    return result
