"""A shared daily allowance and a deterministic, fair plan across exams."""

from collections import deque
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import current_app
from ..db import get_db
from .learning import activities_for, today_date
from .goals import goal_activities, settings_for, order_for_learning


def daily_budget(uid):
    row = (
        get_db()
        .execute("SELECT budget FROM daily_preferences WHERE user_id=?", (uid,))
        .fetchone()
    )
    return row["budget"] if row else 20


def studied_minutes(uid, day=None):
    import json

    day = day or today_date()
    tz = ZoneInfo(current_app.config["TIMEZONE"])
    rows = get_db().execute(
        "SELECT r.created_at,i.snapshot_json FROM reviews r JOIN session_items i ON i.id=r.item_id WHERE r.user_id=?",
        (uid,),
    )
    return sum(
        json.loads(r["snapshot_json"]).get("minutes", 0)
        for r in rows
        if datetime.fromisoformat(r["created_at"]).astimezone(tz).date() == day
    )


def future_goals(uid, day=None):
    return (
        get_db()
        .execute(
            """SELECT g.*,w.name workspace_name FROM goals g JOIN workspaces w ON w.id=g.workspace_id
        WHERE g.user_id=? AND g.completed=0 AND g.target_date>=?
        AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='workspace' AND cs.content_id=w.id)
        ORDER BY g.target_date,g.created_at,g.id""",
            (uid, (day or today_date()).isoformat()),
        )
        .fetchall()
    )


def day_plan(uid, budget=None, day=None, kinds=None):
    day = day or today_date()
    budget = daily_budget(uid) if budget is None else budget
    goals = future_goals(uid, day)
    queues = []
    caps = {}
    if goals:
        for goal in goals:
            if day.weekday() not in settings_for(goal)["weekdays"]:
                continue
            rows = [a for a in goal_activities(goal) if not kinds or a["kind"] in kinds]
            for a in rows:
                a["goal_title"] = goal["title"]
                # Evaluate the next planned date when showing the coming week.
                a["state"] = (
                    "new"
                    if not a["reviews"]
                    else ("due" if a["due_date"] <= day.isoformat() else "scheduled")
                )
            queues.append((goal["id"], rows))
            caps[goal["id"]] = goal["daily_minutes"]
    else:
        queues.append(
            (
                "Wszystkie przedmioty",
                [a for a in activities_for(uid) if not kinds or a["kind"] in kinds],
            )
        )
    pending = any(
        a["state"] == "due" or not a["reviews"] or a["last_grade"] < 2
        for _, rows in queues
        for a in rows
    )
    pools = [
        (
            title,
            deque(
                order_for_learning(
                    [
                        a
                        for a in rows
                        if not pending
                        or a["state"] == "due"
                        or not a["reviews"]
                        or a["last_grade"] < 2
                    ]
                )
            ),
        )
        for title, rows in queues
    ]
    selected, seen, allocations = [], set(), {}
    allocated_by_goal = {}
    total = 0
    # One exercise per goal in each round; overlapping goals never duplicate it.
    while any(q for _, q in pools) and len(selected) < 30:
        for title, q in pools:
            if len(selected) >= 30:
                break
            while q:
                a = q.popleft()
                if a["id"] in seen:
                    continue
                if total + a["minutes"] <= budget and allocated_by_goal.get(
                    title, 0
                ) + a["minutes"] <= caps.get(title, budget):
                    selected.append(a)
                    seen.add(a["id"])
                    total += a["minutes"]
                    allocated_by_goal[title] = (
                        allocated_by_goal.get(title, 0) + a["minutes"]
                    )
                    label = a.get("goal_title", "Wszystkie przedmioty")
                    allocations[label] = allocations.get(label, 0) + a["minutes"]
                    break
    # Long tasks remain explicit; never claim that they fit a short allowance.
    if not selected and budget > 0:
        candidates = [a for _, rows in queues for a in rows]
        if candidates:
            a = order_for_learning(candidates)[0]
            selected = [a]
            total = a["minutes"]
            allocations[a.get("goal_title", "Wszystkie przedmioty")] = total
    return {
        "items": selected,
        "minutes": total,
        "allocations": allocations,
        "budget": budget,
        "goals": goals,
        "overflow": total > budget,
    }


def week_plan(uid):
    """Allocate each next attempt once, never before its scheduled review day."""
    result, workload, tasks_by_id = [], {}, {}
    today = today_date()
    for goal in future_goals(uid):
        tasks = []
        for activity in order_for_learning(goal_activities(goal)):
            if (
                not activity["reviews"]
                or activity["last_grade"] < 2
                or activity["due_date"] <= goal["target_date"]
            ):
                task = tasks_by_id.setdefault(
                    activity["id"],
                    {
                        "minutes": activity["minutes"],
                        "ready": (
                            today.isoformat()
                            if not activity["reviews"] or activity["last_grade"] < 2
                            else activity["due_date"]
                        ),
                    },
                )
                tasks.append(task)
        workload[goal["id"]] = tasks
    for offset in range(7):
        day = today + timedelta(days=offset)
        left = max(0, daily_budget(uid) - (studied_minutes(uid) if offset == 0 else 0))
        combined, allocated = {}, {}
        goals = [
            g
            for g in future_goals(uid, day)
            if day.weekday() in settings_for(g)["weekdays"]
        ]
        while left and goals:
            for goal in list(goals):
                ready = [
                    t
                    for t in workload.get(goal["id"], [])
                    if t["minutes"] > 0 and t["ready"] <= day.isoformat()
                ]
                room = goal["daily_minutes"] - allocated.get(goal["id"], 0)
                amount = min(5, left, room, sum(t["minutes"] for t in ready))
                if not amount:
                    goals.remove(goal)
                    continue
                remaining = amount
                for task in ready:
                    portion = min(task["minutes"], remaining)
                    task["minutes"] -= portion
                    remaining -= portion
                    if not remaining:
                        break
                allocated[goal["id"]] = allocated.get(goal["id"], 0) + amount
                combined[goal["title"]] = combined.get(goal["title"], 0) + amount
                left -= amount
                if not left:
                    break
        result.append(
            {
                "date": day.strftime("%d.%m"),
                "allocations": combined,
                "minutes": sum(combined.values()),
            }
        )
    return result


def balanced_exam(pool, count):
    """Sample by topics rather than excluding longer questions by their duration."""
    import random

    groups = {}
    for a in pool:
        groups.setdefault(a["topic_id"], []).append(a)
    rng = random.SystemRandom()
    queues = list(groups.values())
    for q in queues:
        rng.shuffle(q)
    rng.shuffle(queues)
    chosen = []
    while queues and len(chosen) < count:
        for q in list(queues):
            chosen.append(q.pop())
            if not q:
                queues.remove(q)
            if len(chosen) == count:
                break
    return chosen
