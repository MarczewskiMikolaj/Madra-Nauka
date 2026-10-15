"""Goal scope, availability and honest workload estimates."""

import json
from datetime import date, timedelta
from flask import request
from ..db import get_db
from .learning import activities_for, today_date

DAYS = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]


def settings_for(goal):
    db = get_db()
    row = db.execute(
        "SELECT * FROM goal_settings WHERE goal_id=?", (goal["id"],)
    ).fetchone()
    return {
        "weekdays": json.loads(row["weekdays_json"]) if row else list(range(7)),
        "all_topics": bool(row["all_topics"]) if row else True,
    }


def scope_topics(goal):
    settings = settings_for(goal)
    rows = (
        get_db()
        .execute(
            "SELECT t.*,COALESCE(gt.priority,1) priority FROM topics t LEFT JOIN goal_topics gt ON gt.topic_id=t.id AND gt.goal_id=? WHERE t.workspace_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='topic' AND cs.content_id=t.id) AND (? OR gt.topic_id IS NOT NULL) ORDER BY priority DESC,t.name",
            (goal["id"], goal["workspace_id"], int(settings["all_topics"])),
        )
        .fetchall()
    )
    return [dict(r) for r in rows]


def goal_activities(goal):
    topics = scope_topics(goal)
    priorities = {t["id"]: t["priority"] for t in topics}
    rows = [
        a
        for a in activities_for(goal["user_id"], workspace_id=goal["workspace_id"])
        if a["topic_id"] in priorities
    ]
    for a in rows:
        a["priority"] = priorities[a["topic_id"]]
    return rows


def save_goal_settings(db, goal):
    if request.form.get("schedule_configured") != "1":
        return
    try:
        weekdays = sorted(set(int(x) for x in request.form.getlist("weekdays")))
    except ValueError:
        raise ValueError("Wybierz poprawne dni nauki.") from None
    if not weekdays or any(x not in range(7) for x in weekdays):
        raise ValueError("Wybierz przynajmniej jeden dzień nauki.")
    all_topics = request.form.get("all_topics") == "1"
    chosen = set(request.form.getlist("topic_ids"))
    owned = {
        r["id"]
        for r in db.execute(
            "SELECT id FROM topics WHERE workspace_id=?", (goal["workspace_id"],)
        )
    }
    if not all_topics and (not chosen or not chosen <= owned):
        raise ValueError("Wybierz tematy należące do przedmiotu celu.")
    weights = {}
    for tid in chosen if not all_topics else owned:
        try:
            weight = int(request.form.get("priority_" + tid, 1))
        except ValueError:
            raise ValueError("Ważność tematu: od 1 do 3.") from None
        if not 1 <= weight <= 3:
            raise ValueError("Ważność tematu: od 1 do 3.")
        weights[tid] = weight
    db.execute(
        "INSERT INTO goal_settings VALUES (?,?,?) ON CONFLICT(goal_id) DO UPDATE SET weekdays_json=excluded.weekdays_json,all_topics=excluded.all_topics",
        (goal["id"], json.dumps(weekdays), int(all_topics)),
    )
    db.execute("DELETE FROM goal_topics WHERE goal_id=?", (goal["id"],))
    for tid, weight in weights.items():
        db.execute("INSERT INTO goal_topics VALUES (?,?,?)", (goal["id"], tid, weight))


def enrich_goal(goal):
    goal = dict(goal)
    activities = goal_activities(goal)
    topics = scope_topics(goal)
    today = today_date()
    target = date.fromisoformat(goal["target_date"])
    settings = settings_for(goal)
    new = [a for a in activities if not a["reviews"]]
    weak = [a for a in activities if a["reviews"] and a["last_grade"] < 2]
    reviews = [
        a
        for a in activities
        if a["reviews"] and a["last_grade"] >= 2 and a["due_date"] <= target.isoformat()
    ]
    # One next attempt per exercise; future repetitions depend on future answers.
    immediate = sum(a["minutes"] for a in new + weak)
    demand = immediate + sum(a["minutes"] for a in reviews)
    available = sum(
        (today + timedelta(days=i)).weekday() in settings["weekdays"]
        for i in range(max(0, (target - today).days + 1))
    )
    left = immediate
    week = []
    pending_reviews = list(reviews)
    for i in range(7):
        day = today + timedelta(days=i)
        amount = 0
        learning_day = (
            day.weekday() in settings["weekdays"]
            and day <= target
            and not goal["completed"]
        )
        if learning_day:
            ready = [a for a in pending_reviews if a["due_date"] <= day.isoformat()]
            for a in ready:
                left += a["minutes"]
                pending_reviews.remove(a)
            amount = min(goal["daily_minutes"], left)
            left -= amount
        week.append(
            {
                "date": day.strftime("%d.%m"),
                "minutes": amount,
                "available": learning_day,
            }
        )
    topic_status = []
    for t in topics:
        group = [a for a in activities if a["topic_id"] == t["id"]]
        t.update(
            total=len(group),
            new=sum(not a["reviews"] for a in group),
            weak=sum(bool(a["reviews"]) and a["last_grade"] < 2 for a in group),
            good=sum(bool(a["reviews"]) and a["last_grade"] >= 2 for a in group),
        )
        topic_status.append(t)
    practiced = sum(bool(a["reviews"]) for a in activities)
    goal.update(
        total=len(activities),
        practiced=practiced,
        coverage=round(practiced / len(activities) * 100) if activities else 0,
        days=(target - today).days,
        estimated_remaining=demand,
        feasible=bool(activities) and demand <= available * goal["daily_minutes"],
        week=week,
        review_minutes=sum(a["minutes"] for a in activities if a["state"] == "due"),
        weak=len(weak),
        new=len(new),
        unchecked_topics=sum(t["total"] == 0 for t in topics),
        topic_status=topic_status,
        settings=settings,
        available_days=available,
        today_available=today.weekday() in settings["weekdays"],
        requirements=[
            dict(r)
            for r in get_db().execute(
                "SELECT r.*,t.name topic_name FROM goal_requirements r LEFT JOIN topics t ON t.id=r.topic_id WHERE r.goal_id=? ORDER BY r.created_at,r.id",
                (goal["id"],),
            )
        ],
    )
    return goal


def nearest_goal(uid):
    return (
        get_db()
        .execute(
            """SELECT * FROM goals WHERE user_id=? AND completed=0 AND target_date>=?
            AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='workspace' AND cs.content_id=goals.workspace_id)
            ORDER BY target_date,created_at LIMIT 1""",
            (uid, today_date().isoformat()),
        )
        .fetchone()
    )


def order_for_learning(activities):
    # Alternate topics within the same urgency, retaining importance ordering.
    result = []
    for category in range(4):
        pool = [
            a
            for a in activities
            if (
                0
                if a["state"] == "due"
                else (
                    1
                    if a["reviews"] and a["last_grade"] < 2
                    else 2 if not a["reviews"] else 3
                )
            )
            == category
        ]
        pool.sort(
            key=lambda a: (-a.get("priority", 1), a["due_date"] or "", a["created_at"])
        )
        while pool:
            seen = set()
            rest = []
            for a in pool:
                if a["topic_id"] not in seen:
                    result.append(a)
                    seen.add(a["topic_id"])
                else:
                    rest.append(a)
            pool = rest
    return result


def choose_learning(activities, budget, mode="regular"):
    if mode == "difficult":
        activities = [a for a in activities if a["reviews"] and a["last_grade"] < 2]
    elif mode != "exam":
        pending = [
            a
            for a in activities
            if a["state"] == "due" or not a["reviews"] or a["last_grade"] < 2
        ]
        activities = pending or activities
    pool = order_for_learning(activities)
    if mode == "exam":
        import random

        random.SystemRandom().shuffle(pool)
    chosen = []
    total = 0
    for a in pool:
        if total + a["minutes"] <= budget and len(chosen) < 30:
            chosen.append(a)
            total += a["minutes"]
    return chosen or pool[:1]
