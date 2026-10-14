import json
from urllib.parse import urlparse
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
from .services.exercises import save_support
from .services.notes import note_chapters
from .services.learning import (
    KIND_DIMENSION,
    KINDS,
    activities_for,
    dimension_scores,
    now_iso,
)

bp = Blueprint("library", __name__)
COLORS = {
    "blue": "Niebieski",
    "green": "Zielony",
    "purple": "Fioletowy",
    "amber": "Bursztynowy",
}


def owned_workspace(wid):
    row = (
        get_db()
        .execute(
            "SELECT * FROM workspaces WHERE id=? AND user_id=?", (wid, g.user["id"])
        )
        .fetchone()
    )
    if not row:
        abort(404)
    return row


def owned_topic(tid):
    row = (
        get_db()
        .execute(
            """SELECT t.*,w.name workspace_name,w.color,w.user_id FROM topics t
                             JOIN workspaces w ON w.id=t.workspace_id WHERE t.id=? AND w.user_id=?""",
            (tid, g.user["id"]),
        )
        .fetchone()
    )
    if not row:
        abort(404)
    return row


def owned_content(table, cid):
    if table not in ("materials", "activities"):
        raise ValueError("Unsupported content table")
    row = (
        get_db()
        .execute(
            f"""SELECT c.* FROM {table} c JOIN topics t ON t.id=c.topic_id
                              JOIN workspaces w ON w.id=t.workspace_id WHERE c.id=? AND w.user_id=?""",
            (cid, g.user["id"]),
        )
        .fetchone()
    )
    if not row:
        abort(404)
    return row


def required_text(name, label, max_length=200):
    value = request.form.get(name, "").strip()
    if not value or len(value) > max_length:
        raise ValueError(f"{label}: wpisz od 1 do {max_length} znaków.")
    return value


@bp.get("/biblioteka")
@login_required
def index():
    query = request.args.get("q", "").strip()[:200]
    spaces = (
        get_db()
        .execute(
            """SELECT w.*,(SELECT COUNT(*) FROM topics t WHERE t.workspace_id=w.id) topic_count,
                   (SELECT COUNT(*) FROM activities a JOIN topics t ON t.id=a.topic_id
                    WHERE t.workspace_id=w.id AND a.archived=0) activity_count,
                   (SELECT COUNT(*) FROM materials m JOIN topics t ON t.id=m.topic_id
                    WHERE t.workspace_id=w.id) material_count
                   FROM workspaces w WHERE user_id=? ORDER BY created_at DESC""",
            (g.user["id"],),
        )
        .fetchall()
    )
    if query:
        spaces = [
            w
            for w in spaces
            if query.casefold() in (w["name"] + " " + w["description"]).casefold()
        ]
    results = []
    if query:
        needle = query.casefold()
        queries = [
            (
                "Temat",
                "library.topic",
                "tid",
                "SELECT t.id,t.name title,t.description body,w.name context FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
            ),
            (
                "Materiał",
                "library.material",
                "mid",
                "SELECT m.id,m.title,m.content body,w.name || ' / ' || t.name context FROM materials m JOIN topics t ON t.id=m.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=?",
            ),
            (
                "Ćwiczenie",
                "library.activity_form",
                "aid",
                "SELECT a.id,a.prompt title,a.answer body,w.name || ' / ' || t.name context FROM activities a JOIN topics t ON t.id=a.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND a.archived=0",
            ),
        ]
        for label, endpoint, parameter, sql in queries:
            for row in get_db().execute(sql, (g.user["id"],)):
                if (
                    needle
                    in (
                        row["title"] + " " + row["body"] + " " + row["context"]
                    ).casefold()
                ):
                    results.append(
                        {
                            "kind": label,
                            "title": row["title"],
                            "context": row["context"],
                            "url": url_for(endpoint, **{parameter: row["id"]}),
                        }
                    )
                    if len(results) == 50:
                        break
            if len(results) == 50:
                break
    return render_template(
        "library.html",
        spaces=spaces,
        query=query,
        results=results,
        nav="library",
        uploads=get_db()
        .execute(
            "SELECT u.id,u.filename,u.imported_at,json_extract(u.draft_json,'$.generator') AS generator,(SELECT state FROM ai_jobs j WHERE j.upload_id=u.id ORDER BY created_at DESC LIMIT 1) AS ai_state FROM uploads u WHERE u.user_id=? ORDER BY u.created_at DESC",
            (g.user["id"],),
        )
        .fetchall(),
    )


@bp.route("/przedmioty/nowy", methods=["GET", "POST"])
@bp.route("/przedmioty/<wid>/edytuj", methods=["GET", "POST"])
@login_required
def workspace_form(wid=None):
    record = owned_workspace(wid) if wid else None
    if request.method == "POST":
        try:
            name = required_text("name", "Nazwa", 100)
            description = request.form.get("description", "").strip()[:2000]
            color = request.form.get("color", "blue")
            if color not in COLORS:
                raise ValueError("Wybierz kolor z listy.")
            with transaction() as db:
                if wid:
                    db.execute(
                        "UPDATE workspaces SET name=?,description=?,color=? WHERE id=?",
                        (name, description, color, wid),
                    )
                else:
                    wid = uuid4().hex
                    db.execute(
                        "INSERT INTO workspaces VALUES (?,?,?,?,?,?,NULL)",
                        (wid, g.user["id"], name, description, color, now_iso()),
                    )
            flash("Przedmiot został zapisany.", "success")
            return redirect(url_for("library.workspace", wid=wid))
        except ValueError as e:
            flash(str(e), "error")
    return render_template(
        "form.html", form_type="workspace", record=record, colors=COLORS, nav="library"
    )


@bp.get("/przedmioty/<wid>")
@login_required
def workspace(wid):
    space = owned_workspace(wid)
    topics = (
        get_db()
        .execute(
            """SELECT t.*,(SELECT COUNT(*) FROM materials m WHERE m.topic_id=t.id) material_count,
                              (SELECT COUNT(*) FROM activities a WHERE a.topic_id=t.id AND a.archived=0) activity_count
                              FROM topics t WHERE workspace_id=? ORDER BY created_at""",
            (wid,),
        )
        .fetchall()
    )
    activities = activities_for(g.user["id"], workspace_id=wid)
    return render_template(
        "workspace.html",
        space=space,
        topics=topics,
        activities=activities,
        scores=dimension_scores(activities),
        nav="library",
    )


@bp.route("/przedmioty/<wid>/tematy/nowy", methods=["GET", "POST"])
@bp.route("/tematy/<tid>/edytuj", methods=["GET", "POST"])
@login_required
def topic_form(wid=None, tid=None):
    record = owned_topic(tid) if tid else None
    space = owned_workspace(record["workspace_id"] if record else wid)
    if request.method == "POST":
        try:
            name = required_text("name", "Nazwa", 150)
            description = request.form.get("description", "").strip()[:2000]
            with transaction() as db:
                if tid:
                    db.execute(
                        "UPDATE topics SET name=?,description=? WHERE id=?",
                        (name, description, tid),
                    )
                else:
                    tid = uuid4().hex
                    db.execute(
                        "INSERT INTO topics VALUES (?,?,?,?,?)",
                        (tid, space["id"], name, description, now_iso()),
                    )
            return redirect(url_for("library.topic", tid=tid))
        except ValueError as e:
            flash(str(e), "error")
    return render_template(
        "form.html", form_type="topic", record=record, space=space, nav="library"
    )


@bp.get("/tematy/<tid>")
@login_required
def topic(tid):
    topic = owned_topic(tid)
    materials = (
        get_db()
        .execute(
            "SELECT * FROM materials WHERE topic_id=? ORDER BY created_at DESC", (tid,)
        )
        .fetchall()
    )
    activities = activities_for(g.user["id"], topic_id=tid)
    return render_template(
        "topic.html",
        topic=topic,
        sources=get_db()
        .execute(
            "SELECT id,filename FROM uploads WHERE topic_id=? AND user_id=? AND imported_at IS NOT NULL",
            (tid, g.user["id"]),
        )
        .fetchall(),
        materials=materials,
        activities=activities,
        archived=get_db()
        .execute(
            "SELECT * FROM activities WHERE topic_id=? AND archived=1 ORDER BY updated_at DESC",
            (tid,),
        )
        .fetchall(),
        scores=dimension_scores(activities),
        nav="library",
    )


@bp.get("/materialy/<mid>")
@login_required
def material(mid):
    record = owned_content("materials", mid)
    topic = owned_topic(record["topic_id"])
    return render_template("material.html", material=record, topic=topic, nav="library")


@bp.route("/tematy/<tid>/materialy/nowy", methods=["GET", "POST"])
@bp.route("/materialy/<mid>/edytuj", methods=["GET", "POST"])
@login_required
def material_form(tid=None, mid=None):
    record = owned_content("materials", mid) if mid else None
    topic = owned_topic(record["topic_id"] if record else tid)
    if request.method == "POST":
        try:
            title = required_text("title", "Tytuł", 200)
            kind = request.form.get("kind", "note")
            content = required_text("content", "Treść", 150000)
            if kind not in ("note", "link"):
                raise ValueError("Wybierz notatkę lub link.")
            if kind == "link":
                parsed = urlparse(content)
                if (
                    parsed.scheme not in ("http", "https")
                    or not parsed.hostname
                    or parsed.username
                    or any(c.isspace() for c in content)
                ):
                    raise ValueError(
                        "Wpisz pełny link zaczynający się od https:// lub http://."
                    )
            with transaction() as db:
                if mid:
                    db.execute(
                        "UPDATE materials SET title=?,kind=?,content=?,updated_at=? WHERE id=?",
                        (title, kind, content, now_iso(), mid),
                    )
                else:
                    mid = uuid4().hex
                    db.execute(
                        "INSERT INTO materials VALUES (?,?,?,?,?,?,?)",
                        (mid, topic["id"], kind, title, content, now_iso(), now_iso()),
                    )
            flash("Materiał został zapisany.", "success")
            return redirect(url_for("library.topic", tid=topic["id"]))
        except ValueError as e:
            flash(str(e), "error")
    return render_template(
        "form.html", form_type="material", record=record, topic=topic, nav="library"
    )


@bp.route("/tematy/<tid>/cwiczenia/nowe", methods=["GET", "POST"])
@bp.route("/cwiczenia/<aid>/edytuj", methods=["GET", "POST"])
@login_required
def activity_form(tid=None, aid=None):
    record = owned_content("activities", aid) if aid else None
    topic = owned_topic(record["topic_id"] if record else tid)
    if request.method == "POST":
        try:
            kind = request.form.get("kind", "flashcard")
            if kind not in KINDS:
                raise ValueError("Wybierz typ ćwiczenia.")
            prompt = required_text("prompt", "Polecenie", 10000)
            answer = required_text("answer", "Odpowiedź wzorcowa", 10000)
            try:
                minutes = int(request.form.get("minutes", 2))
            except ValueError:
                minutes = 0
            if not 1 <= minutes <= 15:
                raise ValueError("Czas ćwiczenia musi wynosić od 1 do 15 minut.")
            options = (
                [
                    x.strip()
                    for x in request.form.get("options", "").splitlines()
                    if x.strip()
                ]
                if kind == "quiz"
                else []
            )
            if kind == "quiz" and (
                not 2 <= len(options) <= 6
                or len(set(options)) != len(options)
                or answer not in options
                or any(len(x) > 1000 for x in options)
            ):
                raise ValueError(
                    "Quiz: dodaj 2–6 różnych opcji, po jednej w wierszu. Odpowiedź musi dokładnie odpowiadać jednej z nich."
                )
            if kind == "cloze" and "[...]" not in prompt:
                raise ValueError("Oznacz lukę w poleceniu jako [...].")
            from .services.exercises import validate_exercise

            help_data = validate_exercise(
                {
                    "kind": kind,
                    "prompt": prompt,
                    "answer": answer,
                    "options": options,
                    "minutes": minutes,
                    "hints": request.form.getlist("hints"),
                    "explanation": request.form.get("explanation", ""),
                    "rubric": request.form.get("rubric", ""),
                }
            )
            material_id = request.form.get("material_id") or None
            try:
                chapter = int(request.form.get("source_chapter", 0) or 0)
            except ValueError:
                raise ValueError("Wybierz numer rozdziału źródła.") from None
            if material_id:
                material = owned_content("materials", material_id)
                if material["topic_id"] != topic["id"] or not 0 <= chapter <= len(
                    note_chapters(material["content"])
                ):
                    raise ValueError(
                        "Źródło musi należeć do tego tematu, z poprawnym numerem rozdziału."
                    )
            elif chapter:
                raise ValueError("Najpierw wybierz notatkę źródłową.")
            with transaction() as db:
                if aid:
                    db.execute(
                        """UPDATE activities SET kind=?,dimension=?,prompt=?,answer=?,options_json=?,minutes=?,updated_at=? WHERE id=?""",
                        (
                            kind,
                            KIND_DIMENSION[kind],
                            prompt,
                            answer,
                            json.dumps(options),
                            minutes,
                            now_iso(),
                            aid,
                        ),
                    )
                else:
                    aid = uuid4().hex
                    db.execute(
                        """INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,0,NULL,?,?)""",
                        (
                            aid,
                            topic["id"],
                            kind,
                            KIND_DIMENSION[kind],
                            prompt,
                            answer,
                            json.dumps(options),
                            minutes,
                            now_iso(),
                            now_iso(),
                        ),
                    )
                save_support(db, aid, help_data, material_id, chapter)
            flash("Ćwiczenie zostało zapisane.", "success")
            return redirect(url_for("library.topic", tid=topic["id"]))
        except ValueError as e:
            flash(str(e), "error")
    options = "\n".join(json.loads(record["options_json"])) if record else ""
    support = (
        get_db()
        .execute("SELECT * FROM activity_support WHERE activity_id=?", (aid,))
        .fetchone()
        if aid
        else None
    )
    support = dict(support) if support else {}
    support["hints"] = json.loads(support.get("hints_json") or "[]")
    materials = (
        get_db()
        .execute(
            "SELECT * FROM materials WHERE topic_id=? ORDER BY title", (topic["id"],)
        )
        .fetchall()
    )
    return render_template(
        "form.html",
        form_type="activity",
        support=support,
        materials=materials,
        record=record,
        topic=topic,
        options=options,
        nav="library",
    )


@bp.post("/cwiczenia/<aid>/archiwizuj")
@login_required
def archive_activity(aid):
    record = owned_content("activities", aid)
    with transaction() as db:
        db.execute("UPDATE activities SET archived=1 WHERE id=?", (aid,))
    flash("Ćwiczenie zarchiwizowane. Historia została zachowana.", "success")
    return redirect(url_for("library.topic", tid=record["topic_id"]))


@bp.post("/cwiczenia/<aid>/przywroc")
@login_required
def restore_activity(aid):
    record = owned_content("activities", aid)
    with transaction() as db:
        db.execute("UPDATE activities SET archived=0 WHERE id=?", (aid,))
    flash("Ćwiczenie przywrócone wraz z jego historią i terminem powtórki.", "success")
    return redirect(url_for("library.topic", tid=record["topic_id"]))
