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
            """SELECT w.*,(SELECT COUNT(*) FROM topics t WHERE t.workspace_id=w.id AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='topic' AND cs.content_id=t.id)) topic_count,
                   (SELECT COUNT(*) FROM activities a JOIN topics t ON t.id=a.topic_id
                    WHERE t.workspace_id=w.id AND a.archived=0 AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='topic' AND cs.content_id=t.id)) activity_count,
                   (SELECT COUNT(*) FROM materials m JOIN topics t ON t.id=m.topic_id
                    WHERE t.workspace_id=w.id AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (t.id,m.id) AND cs.kind IN ('topic','material')) AND NOT EXISTS (SELECT 1 FROM upload_materials um JOIN content_states cu ON cu.kind='upload' AND cu.content_id=um.upload_id WHERE um.material_id=m.id)) material_count
                   FROM workspaces w WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='workspace' AND cs.content_id=w.id) ORDER BY created_at DESC""",
            (g.user["id"],),
        )
        .fetchall()
    )
    visible_activities = activities_for(g.user["id"])
    spaces = [
        {
            **dict(w),
            "activity_count": sum(
                a["workspace_id"] == w["id"] for a in visible_activities
            ),
        }
        for w in spaces
    ]
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
                "SELECT t.id,t.name title,t.description body,w.name context FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (w.id,t.id) AND cs.kind IN ('workspace','topic'))",
            ),
            (
                "Materiał",
                "library.material",
                "mid",
                "SELECT m.id,m.title,m.content body,w.name || ' / ' || t.name context FROM materials m JOIN topics t ON t.id=m.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND NOT EXISTS (SELECT 1 FROM upload_materials um JOIN content_states cu ON cu.kind='upload' AND cu.content_id=um.upload_id WHERE um.material_id=m.id) AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (w.id,t.id) AND cs.kind IN ('workspace','topic'))",
            ),
            (
                "Ćwiczenie",
                "library.activity_form",
                "aid",
                "SELECT a.id,a.prompt title,a.answer body,w.name || ' / ' || t.name context FROM activities a JOIN topics t ON t.id=a.topic_id JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND a.archived=0 AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (w.id,t.id) AND cs.kind IN ('workspace','topic')) AND NOT EXISTS (SELECT 1 FROM activity_support s JOIN content_states cs ON cs.kind='material' AND cs.content_id=s.material_id WHERE s.activity_id=a.id) AND NOT EXISTS (SELECT 1 FROM upload_activities ua JOIN content_states cs ON cs.kind='upload' AND cs.content_id=ua.upload_id WHERE ua.activity_id=a.id)",
            ),
        ]
        for label, endpoint, parameter, sql in queries:
            for row in get_db().execute(sql, (g.user["id"],)):
                if (
                    not get_db()
                    .execute(
                        "SELECT 1 FROM content_states WHERE kind='material' AND content_id=?",
                        (row["id"],),
                    )
                    .fetchone()
                    and needle
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
    topics_by_workspace = {}
    for topic in get_db().execute(
        """SELECT t.* FROM topics t JOIN workspaces w ON w.id=t.workspace_id
           WHERE w.user_id=? AND NOT EXISTS (
               SELECT 1 FROM content_states cs
               WHERE (cs.kind='workspace' AND cs.content_id=w.id)
                  OR (cs.kind='topic' AND cs.content_id=t.id))
           ORDER BY t.created_at""",
        (g.user["id"],),
    ):
        topics_by_workspace.setdefault(topic["workspace_id"], []).append(
            {
                **dict(topic),
                "activity_count": sum(
                    a["topic_id"] == topic["id"] for a in visible_activities
                ),
            }
        )
    return render_template(
        "library.html",
        topics_by_workspace=topics_by_workspace,
        spaces=spaces,
        query=query,
        results=results,
        nav="library",
        uploads=get_db()
        .execute(
            "SELECT u.id,u.filename,u.imported_at,json_extract(u.draft_json,'$.generator') AS generator,(SELECT state FROM ai_jobs j WHERE j.upload_id=u.id ORDER BY created_at DESC LIMIT 1) AS ai_state FROM uploads u WHERE u.user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.content_id IN (u.id,u.topic_id,u.workspace_id)) AND (?='' OR instr(lower(u.filename),lower(?))>0) ORDER BY u.created_at DESC",
            (g.user["id"], query, query),
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
    owned_workspace(wid)
    return redirect(url_for("library.index", _anchor="subject-" + wid))


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
            "SELECT * FROM materials m WHERE topic_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='material' AND cs.content_id=m.id) AND NOT EXISTS (SELECT 1 FROM upload_materials um JOIN content_states cu ON cu.kind='upload' AND cu.content_id=um.upload_id WHERE um.material_id=m.id) ORDER BY created_at DESC",
            (tid,),
        )
        .fetchall()
    )
    activities = activities_for(g.user["id"], topic_id=tid)
    for activity in activities:
        activity["options"] = json.loads(activity["options_json"])
    return render_template(
        "topic.html",
        topic=topic,
        sources=get_db()
        .execute(
            "SELECT id,filename FROM uploads u WHERE topic_id=? AND user_id=? AND imported_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='upload' AND cs.content_id=u.id)",
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
    progress = (
        get_db()
        .execute(
            "SELECT * FROM reading_progress WHERE material_id=? AND user_id=? ORDER BY updated_at DESC LIMIT 1",
            (mid, g.user["id"]),
        )
        .fetchone()
    )
    return render_template(
        "material.html",
        material=record,
        topic=topic,
        reading=progress,
        reading_done=[
            r[0]
            for r in get_db().execute(
                "SELECT chapter FROM reading_progress WHERE material_id=? AND user_id=? AND completed=1",
                (mid, g.user["id"]),
            )
        ],
        nav="library",
    )


@bp.route("/tematy/<tid>/materialy/nowy", methods=["GET", "POST"])
@bp.route("/materialy/<mid>/edytuj", methods=["GET", "POST"])
@login_required
def material_form(tid=None, mid=None):
    record = owned_content("materials", mid) if mid else None
    topic = owned_topic(record["topic_id"] if record else tid)
    from .workflow import form_draft, check_form_revision

    key = "note:" + mid if mid else "newnote:" + tid
    draft = form_draft(key)
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
                check_form_revision(key)
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
                db.execute(
                    "DELETE FROM form_drafts WHERE user_id=? AND draft_key=?",
                    (g.user["id"], key),
                )
            flash("Materiał został zapisany.", "success")
            return redirect(url_for("library.topic", tid=topic["id"]))
        except ValueError as e:
            flash(str(e), "error")
    if request.method == "GET" and draft["revision"]:
        record = {
            **(dict(record) if record else {}),
            **json.loads(draft["payload_json"]),
        }
    return render_template(
        "form.html",
        form_type="material",
        record=record,
        topic=topic,
        draft_key=key,
        draft_revision=draft["revision"],
        nav="library",
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
            answer = request.form.get("answer", "").strip()
            if kind == "quiz" and request.form.get("correct_option") is not None:
                try:
                    raw_options = request.form.get("options", "").splitlines()
                    correct_index = int(request.form["correct_option"])
                    if not 0 <= correct_index < len(raw_options):
                        raise ValueError("Wybierz poprawny wariant quizu.")
                    answer = raw_options[correct_index].strip()
                except (ValueError, IndexError):
                    raise ValueError("Wybierz poprawny wariant quizu.") from None
            if not answer or len(answer) > 10000:
                raise ValueError("Wpisz odpowiedź wzorcową.")
            image = request.files.get("question_image")
            image_data = None
            if image and image.filename:
                from .workflow import clean_image

                image_data = clean_image(image.read(5 * 1024 * 1024 + 1))
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
                if request.form.get("remove_image") == "1":
                    db.execute(
                        "DELETE FROM activity_images WHERE activity_id=?", (aid,)
                    )
                if image_data:
                    image_id = uuid4().hex
                    db.execute(
                        "INSERT INTO image_assets VALUES (?,?,?,?)",
                        (image_id, g.user["id"], image_data, now_iso()),
                    )
                    db.execute(
                        "INSERT INTO activity_images VALUES (?,?) ON CONFLICT(activity_id) DO UPDATE SET asset_id=excluded.asset_id",
                        (aid, image_id),
                    )
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
    if not aid and request.args.get("material_id"):
        source = owned_content("materials", request.args["material_id"])
        if source["topic_id"] != topic["id"]:
            abort(400)
        support["material_id"] = source["id"]
        try:
            support["source_chapter"] = int(request.args.get("chapter", 0))
        except ValueError:
            abort(400)
        if not 0 <= support["source_chapter"] <= len(note_chapters(source["content"])):
            abort(400)
    image = (
        get_db()
        .execute("SELECT asset_id FROM activity_images WHERE activity_id=?", (aid,))
        .fetchone()
        if aid
        else None
    )
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
        image_id=image["asset_id"] if image else None,
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
