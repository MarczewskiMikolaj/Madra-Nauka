"""Student work: quick notes, drafts, reading and reversible organization."""

import base64
import io
import json
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
    Response,
)
from PIL import Image, ImageOps, UnidentifiedImageError
from .auth import login_required
from .db import get_db, transaction
from .library import owned_workspace, owned_topic, owned_content, required_text
from .services.learning import now_iso
from .services.notes import note_chapters

bp = Blueprint("workflow", __name__)
TABLES = {
    "workspace": "workspaces",
    "topic": "topics",
    "material": "materials",
    "upload": "uploads",
}


def owned(kind, cid):
    if kind == "workspace":
        return owned_workspace(cid)
    if kind == "topic":
        return owned_topic(cid)
    if kind == "material":
        return owned_content("materials", cid)
    if kind == "upload":
        from .uploads import owned_upload

        return owned_upload(cid)
    abort(404)


def draft_key(key):
    if key == "quick:new":
        return
    if key.startswith("recall:"):
        try:
            _, mid, chapter = key.split(":")
            chapter = int(chapter)
        except (ValueError, TypeError):
            abort(400)
        material = owned_content("materials", mid)
        if not 1 <= chapter <= len(note_chapters(material["content"])):
            abort(400)
        return
    prefix, sep, cid = key.partition(":")
    if prefix == "note":
        owned_content("materials", cid)
    elif prefix == "newnote":
        owned_topic(cid)
    else:
        abort(404)


def form_draft(key):
    row = (
        get_db()
        .execute(
            "SELECT * FROM form_drafts WHERE user_id=? AND draft_key=?",
            (g.user["id"], key),
        )
        .fetchone()
    )
    return dict(row) if row else {"payload_json": "{}", "revision": 0}


def check_form_revision(key):
    if "draft_revision" in request.form:
        try:
            revision = int(request.form["draft_revision"])
        except ValueError:
            abort(400)
        if revision != form_draft(key)["revision"]:
            abort(409)


@bp.post("/szkice/notatki")
@login_required
def save_note_draft():
    key = request.form.get("draft_key", "")
    draft_key(key)
    payload = {
        k: request.form.get(k, "")
        for k in (
            "title",
            "content",
            "kind",
            "workspace_id",
            "workspace_name",
            "response",
        )
    }
    if (
        len(payload["content"]) > 150000
        or len(payload["title"]) > 200
        or len(payload["workspace_name"]) > 100
        or len(payload["response"]) > 10000
        or len(payload["workspace_id"]) > 100
        or payload["kind"] not in ("", "note", "link")
    ):
        abort(400)
    with transaction() as db:
        check_form_revision(key)
        revision = form_draft(key)["revision"] + 1
        db.execute(
            """INSERT INTO form_drafts VALUES (?,?,?,?,?) ON CONFLICT(user_id,draft_key) DO UPDATE SET
            payload_json=excluded.payload_json,revision=excluded.revision,updated_at=excluded.updated_at""",
            (
                g.user["id"],
                key,
                json.dumps(payload, ensure_ascii=False),
                revision,
                now_iso(),
            ),
        )
    return {"revision": revision}


@bp.route("/notatki/nowa", methods=["GET", "POST"])
@login_required
def quick_note():
    error = None
    if request.method == "POST":
        try:
            title = required_text("title", "Tytuł", 200)
            content = required_text("content", "Notatka", 150000)
            wid = request.form.get("workspace_id")
            if wid:
                owned_workspace(wid)
            name = (
                request.form.get("workspace_name", "").strip()[:100] or "Moje notatki"
            )
            with transaction() as db:
                check_form_revision("quick:new")
                if not wid:
                    wid = uuid4().hex
                    db.execute(
                        "INSERT INTO workspaces VALUES (?,?,?,?,?,?,NULL)",
                        (wid, g.user["id"], name, "", "blue", now_iso()),
                    )
                tid, mid = uuid4().hex, uuid4().hex
                db.execute(
                    "INSERT INTO topics VALUES (?,?,?,?,?)",
                    (tid, wid, title[:150], "", now_iso()),
                )
                db.execute(
                    "INSERT INTO materials VALUES (?,?,?,?,?,?,?)",
                    (mid, tid, "note", title, content, now_iso(), now_iso()),
                )
                db.execute(
                    "DELETE FROM form_drafts WHERE user_id=? AND draft_key=?",
                    (g.user["id"], "quick:new"),
                )
            return redirect(url_for("library.material", mid=mid))
        except ValueError as exc:
            error = str(exc)
    draft = form_draft("quick:new")
    return render_template(
        "quick_note.html",
        error=error,
        draft=json.loads(draft["payload_json"]),
        revision=draft["revision"],
        spaces=get_db()
        .execute(
            "SELECT * FROM workspaces w WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM content_states s WHERE s.kind='workspace' AND s.content_id=w.id) ORDER BY name",
            (g.user["id"],),
        )
        .fetchall(),
        nav="library",
    )


@bp.route("/notatki/<mid>/cwicz", methods=["GET", "POST"])
@login_required
def recall(mid):
    material = owned_content("materials", mid)
    if material["kind"] != "note":
        abort(400)
    chapters = note_chapters(material["content"])
    try:
        chapter = int(request.values.get("chapter", 1))
    except ValueError:
        abort(400)
    if not 1 <= chapter <= len(chapters):
        abort(404)
    key = "recall:" + mid + ":" + str(chapter)
    draft = form_draft(key)
    response = ""
    stage = request.args.get("stage", "read")
    if stage not in ("read", "recall", "compare"):
        abort(400)
    if request.method == "POST":
        response = request.form.get("response", "").strip()
        if not response or len(response) > 10000:
            abort(400)
        stage = "compare"
        with transaction() as db:
            check_form_revision(key)
            db.execute(
                """INSERT INTO reading_progress VALUES (?,?,?,?,?,?) ON CONFLICT(material_id,user_id,chapter)
                DO UPDATE SET recalled=excluded.recalled,completed=excluded.completed,updated_at=excluded.updated_at""",
                (mid, g.user["id"], chapter, response, 1, now_iso()),
            )
            db.execute(
                "DELETE FROM form_drafts WHERE user_id=? AND draft_key=?",
                (g.user["id"], key),
            )
        return redirect(
            url_for("workflow.recall", mid=mid, chapter=chapter, stage="compare")
        )
    if stage == "compare":
        saved = (
            get_db()
            .execute(
                "SELECT recalled FROM reading_progress WHERE material_id=? AND user_id=? AND chapter=? AND completed=1",
                (mid, g.user["id"], chapter),
            )
            .fetchone()
        )
        if not saved:
            return redirect(
                url_for("workflow.recall", mid=mid, chapter=chapter, stage="recall")
            )
        response = saved["recalled"]
    return render_template(
        "recall.html",
        material=material,
        chapter=chapter,
        entry=chapters[chapter - 1],
        total=len(chapters),
        stage=stage,
        response=response,
        draft_key=key,
        draft_response=json.loads(draft["payload_json"]).get("response", ""),
        draft_revision=draft["revision"],
        nav="library",
    )


@bp.post("/notatki/<mid>/pozycja")
@login_required
def reading_position(mid):
    material = owned_content("materials", mid)
    try:
        chapter = int(request.form.get("chapter", 0))
    except ValueError:
        abort(400)
    if not 1 <= chapter <= len(note_chapters(material["content"])):
        abort(400)
    with transaction() as db:
        db.execute(
            """INSERT INTO reading_progress VALUES (?,?,?,'',0,?) ON CONFLICT(material_id,user_id,chapter) DO UPDATE SET updated_at=excluded.updated_at""",
            (mid, g.user["id"], chapter, now_iso()),
        )
    return {"saved": True}


@bp.get("/notatki/<mid>/pobierz")
@login_required
def download_note(mid):
    material = owned_content("materials", mid)
    from .services.formatting import render_content
    from markupsafe import escape

    # Plain standalone HTML: no login, remote assets, scripts or network required.
    body = (
        '<!doctype html><html lang="pl"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'
        + str(escape(material["title"]))
        + "</title><style>body{max-width:760px;margin:40px auto;padding:20px;font:18px/1.65 system-ui;color:#1c2944}pre,table{overflow:auto;display:block}pre{white-space:pre-wrap}a{overflow-wrap:anywhere}</style><h1>"
        + str(escape(material["title"]))
        + "</h1>"
        + str(render_content(material["content"]))
        + "</html>"
    )
    return Response(
        body,
        mimetype="text/html",
        headers={"Content-Disposition": 'attachment; filename="notatka.html"'},
    )


@bp.post("/porzadek/<kind>/<cid>/status")
@login_required
def state(kind, cid):
    owned(kind, cid)
    action = request.form.get("action")
    if action not in ("archive", "trash", "restore"):
        abort(400)
    if kind == "upload":
        if (
            get_db()
            .execute(
                "SELECT 1 FROM ai_jobs WHERE upload_id=? AND state='running'", (cid,)
            )
            .fetchone()
        ):
            flash("Najpierw zakończ lub anuluj opracowanie tego pliku.", "info")
            return redirect(url_for("uploads.preview", uid=cid))
    with transaction() as db:
        if action == "restore":
            db.execute(
                "DELETE FROM content_states WHERE kind=? AND content_id=? AND user_id=?",
                (kind, cid, g.user["id"]),
            )
        else:
            db.execute(
                "INSERT INTO content_states VALUES (?,?,?,?,?) ON CONFLICT(kind,content_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at",
                (
                    g.user["id"],
                    kind,
                    cid,
                    "trashed" if action == "trash" else "archived",
                    now_iso(),
                ),
            )
    flash(
        (
            "Przywrócono element. Sprawdź też, czy jego przedmiot lub temat jest aktywny."
            if action == "restore"
            else "Element przeniesiony do archiwum lub kosza. Możesz go przywrócić."
        ),
        "success",
    )
    return redirect(url_for("workflow.organize"))


@bp.get("/biblioteka/porzadek")
@login_required
def organize():
    rows = []
    for state in get_db().execute(
        "SELECT * FROM content_states WHERE user_id=? ORDER BY updated_at DESC",
        (g.user["id"],),
    ):
        record = (
            get_db()
            .execute(
                f"SELECT * FROM {TABLES[state['kind']]} WHERE id=?",
                (state["content_id"],),
            )
            .fetchone()
        )
        if record:
            name = (
                record["filename"]
                if state["kind"] == "upload"
                else record["title"] if state["kind"] == "material" else record["name"]
            )
            rows.append({**dict(state), "name": name})
    return render_template("organize.html", rows=rows, nav="library")


@bp.post("/porzadek/<kind>/<cid>/przenies")
@login_required
def move(kind, cid):
    if kind not in ("topic", "material", "activity"):
        abort(400)
    record = (
        owned_content("activities", cid) if kind == "activity" else owned(kind, cid)
    )
    destination = request.form.get("destination", "")
    target = (
        owned_workspace(destination) if kind == "topic" else owned_topic(destination)
    )
    with transaction() as db:
        if kind == "topic":
            if target["id"] != record["workspace_id"]:
                # Requirements in the old exam cannot silently follow to another course.
                db.execute(
                    "UPDATE goal_requirements SET topic_id=NULL,checked=0 WHERE topic_id=?",
                    (cid,),
                )
                db.execute("DELETE FROM goal_topics WHERE topic_id=?", (cid,))
                db.execute(
                    "UPDATE topics SET workspace_id=? WHERE id=?", (destination, cid)
                )
                db.execute(
                    "UPDATE uploads SET workspace_id=? WHERE topic_id=?",
                    (destination, cid),
                )
        elif kind == "material":
            db.execute("UPDATE materials SET topic_id=? WHERE id=?", (destination, cid))
            db.execute(
                "UPDATE activity_support SET material_id=NULL,source_chapter=0 WHERE material_id=? AND activity_id IN (SELECT id FROM activities WHERE topic_id<>?)",
                (cid, destination),
            )
        else:
            db.execute(
                "UPDATE activities SET topic_id=? WHERE id=?", (destination, cid)
            )
            db.execute(
                "UPDATE activity_support SET material_id=NULL,source_chapter=0 WHERE activity_id=? AND material_id IN (SELECT id FROM materials WHERE topic_id<>?)",
                (cid, destination),
            )
    flash("Przeniesiono. Dotychczasowe sesje zachowały swoją treść.", "success")
    return redirect(
        url_for("library.workspace", wid=destination)
        if kind == "topic"
        else url_for("library.topic", tid=destination)
    )


def clean_image(data):
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("Wybierz obraz do 5 MB.")
    try:
        with Image.open(io.BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
            if image.width * image.height > 16_000_000:
                raise ValueError("Obraz może mieć do 16 megapikseli.")
            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail((2400, 2400))
            clean = Image.new("RGB", image.size, "white")
            if image.mode == "RGBA":
                clean.paste(image, mask=image.getchannel("A"))
            else:
                clean.paste(image.convert("RGB"))
            output = io.BytesIO()
            clean.save(output, format="PNG")
            return output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
    ) as exc:
        raise ValueError("Nie można odczytać obrazu PNG, JPG lub WebP.") from exc


@bp.get("/obrazy/<asset_id>")
@login_required
def image(asset_id):
    row = (
        get_db()
        .execute(
            "SELECT png FROM image_assets WHERE id=? AND user_id=?",
            (asset_id, g.user["id"]),
        )
        .fetchone()
    )
    if not row:
        abort(404)
    return Response(
        row["png"], mimetype="image/png", headers={"Cache-Control": "private, no-store"}
    )


@bp.get("/tematy/<tid>/eksport-zestawu")
@login_required
def export_topic(tid):
    topic = owned_topic(tid)
    from .services.learning import activities_for

    rows = []
    for a in activities_for(g.user["id"], topic_id=tid):
        item = {
            k: a[k]
            for k in ("kind", "prompt", "answer", "minutes", "explanation", "rubric")
        }
        item.update(
            options=json.loads(a["options_json"]),
            hints=json.loads(a["hints_json"] or "[]"),
        )
        if a["image_id"]:
            blob = (
                get_db()
                .execute(
                    "SELECT png FROM image_assets WHERE id=? AND user_id=?",
                    (a["image_id"], g.user["id"]),
                )
                .fetchone()
            )
            if blob:
                item["image_png"] = base64.b64encode(blob["png"]).decode()
        rows.append(item)
    materials = [
        dict(r)
        for r in get_db().execute(
            "SELECT kind,title,content FROM materials m WHERE topic_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='material' AND cs.content_id=m.id) AND NOT EXISTS (SELECT 1 FROM upload_materials um JOIN content_states cu ON cu.kind='upload' AND cu.content_id=um.upload_id WHERE um.material_id=m.id)",
            (tid,),
        )
    ]
    payload = json.dumps(
        {
            "format": "madra-topic-1",
            "title": topic["name"],
            "materials": materials,
            "activities": rows,
        },
        ensure_ascii=False,
        indent=2,
    )
    if len(payload.encode("utf-8")) > 20 * 1024 * 1024:
        flash(
            "Zestaw przekracza 20 MB. Przenieś część treści do osobnego tematu i pobierz go oddzielnie.",
            "info",
        )
        return redirect(url_for("library.topic", tid=tid))
    return Response(
        payload,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="zestaw-tematu.json"'},
    )


@bp.route("/zestawy/import", methods=["GET", "POST"])
@login_required
def import_topic():
    error = None
    if request.method == "POST":
        try:
            file = request.files.get("file")
            raw = (
                file.read(20 * 1024 * 1024 + 1)
                if file
                else request.form.get("text", "").encode()
            )
            if len(raw) > 20 * 1024 * 1024:
                raise ValueError("Zestaw może mieć do 20 MB.")
            package = json.loads(raw)
            if (
                not isinstance(package, dict)
                or package.get("format") != "madra-topic-1"
            ):
                raise ValueError("Wybierz plik wyeksportowanego tematu Mądrej Nauki.")
            title = package.get("title", "")
            if not isinstance(title, str) or not 1 <= len(title.strip()) <= 150:
                raise ValueError("Nieprawidłowy tytuł zestawu.")
            activities = package.get("activities", [])
            materials = package.get("materials", [])
            if (
                not isinstance(activities, list)
                or len(activities) > 200
                or not isinstance(materials, list)
                or len(materials) > 50
                or not (activities or materials)
            ):
                raise ValueError("Zestaw może mieć 1–200 pytań lub do 50 notatek.")
            from .services.exercises import validate_exercise

            clean = []
            for a in activities:
                item = validate_exercise(a)
                if a.get("image_png"):
                    encoded = a["image_png"]
                    if not isinstance(encoded, str) or len(encoded) > 7 * 1024 * 1024:
                        raise ValueError("Za duży obraz w zestawie.")
                    item["image_png"] = base64.b64encode(
                        clean_image(base64.b64decode(encoded, validate=True))
                    ).decode()
                clean.append(item)
            notes = []
            from urllib.parse import urlsplit

            for m in materials:
                if (
                    not isinstance(m, dict)
                    or m.get("kind") not in ("note", "link")
                    or not isinstance(m.get("title"), str)
                    or not 1 <= len(m["title"]) <= 200
                    or not isinstance(m.get("content"), str)
                    or not 1 <= len(m["content"]) <= 150000
                ):
                    raise ValueError("Nieprawidłowa notatka w zestawie.")
                if m["kind"] == "link":
                    url = urlsplit(m["content"])
                    if (
                        url.scheme not in ("https", "http")
                        or not url.hostname
                        or url.username
                        or any(c.isspace() for c in m["content"])
                    ):
                        raise ValueError("Nieprawidłowy link w zestawie.")
                notes.append({k: m[k] for k in ("kind", "title", "content")})
            wid = request.form.get("workspace_id") or None
            if wid:
                owned_workspace(wid)
            pid = uuid4().hex
            with transaction() as db:
                db.execute(
                    "INSERT INTO topic_packages VALUES (?,?,?,?,NULL,?)",
                    (
                        pid,
                        g.user["id"],
                        json.dumps(
                            {"title": title, "activities": clean, "materials": notes},
                            ensure_ascii=False,
                        ),
                        wid,
                        now_iso(),
                    ),
                )
            return redirect(url_for("workflow.import_topic_preview", pid=pid))
        except (ValueError, TypeError, KeyError, RecursionError) as exc:
            error = (
                str(exc)
                if isinstance(exc, ValueError)
                and not isinstance(exc, json.JSONDecodeError)
                else "Nie można odczytać zestawu. Wybierz poprawny plik JSON."
            )
    return render_template(
        "topic_import.html",
        error=error,
        spaces=get_db()
        .execute(
            "SELECT * FROM workspaces w WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM content_states cs WHERE cs.kind='workspace' AND cs.content_id=w.id) ORDER BY name",
            (g.user["id"],),
        )
        .fetchall(),
        nav="library",
    )


@bp.route("/zestawy/<pid>/podglad", methods=["GET", "POST"])
@login_required
def import_topic_preview(pid):
    package = (
        get_db()
        .execute(
            "SELECT * FROM topic_packages WHERE id=? AND user_id=?", (pid, g.user["id"])
        )
        .fetchone()
    )
    if not package:
        abort(404)
    payload = json.loads(package["payload_json"])
    if request.method == "POST":
        from .services.exercises import insert_exercise

        with transaction() as db:
            package = db.execute(
                "SELECT * FROM topic_packages WHERE id=? AND user_id=?",
                (pid, g.user["id"]),
            ).fetchone()
            if package["imported_topic_id"]:
                return redirect(
                    url_for("library.topic", tid=package["imported_topic_id"])
                )
            wid = package["workspace_id"]
            if not wid:
                wid = uuid4().hex
                db.execute(
                    "INSERT INTO workspaces VALUES (?,?,?,?,?,?,NULL)",
                    (
                        wid,
                        g.user["id"],
                        payload["title"][:100],
                        "Zaimportowany zestaw",
                        "blue",
                        now_iso(),
                    ),
                )
            tid = uuid4().hex
            db.execute(
                "INSERT INTO topics VALUES (?,?,?,?,?)",
                (tid, wid, payload["title"], "", now_iso()),
            )
            for m in payload["materials"]:
                db.execute(
                    "INSERT INTO materials VALUES (?,?,?,?,?,?,?)",
                    (
                        uuid4().hex,
                        tid,
                        m["kind"],
                        m["title"],
                        m["content"],
                        now_iso(),
                        now_iso(),
                    ),
                )
            for a in payload["activities"]:
                aid = insert_exercise(db, tid, a)
                if a.get("image_png"):
                    image_id = uuid4().hex
                    db.execute(
                        "INSERT INTO image_assets VALUES (?,?,?,?)",
                        (
                            image_id,
                            g.user["id"],
                            base64.b64decode(a["image_png"]),
                            now_iso(),
                        ),
                    )
                    db.execute(
                        "INSERT INTO activity_images VALUES (?,?)", (aid, image_id)
                    )
            db.execute(
                "UPDATE topic_packages SET imported_topic_id=? WHERE id=?", (tid, pid)
            )
        return redirect(url_for("library.topic", tid=tid))
    return render_template("topic_import_preview.html", payload=payload, nav="library")


def navigation_data():
    if not g.get("user"):
        return {}
    return {
        "destination_spaces": get_db()
        .execute(
            "SELECT id,name FROM workspaces w WHERE user_id=? AND NOT EXISTS (SELECT 1 FROM content_states s WHERE s.kind='workspace' AND s.content_id=w.id) ORDER BY name",
            (g.user["id"],),
        )
        .fetchall(),
        "destination_topics": get_db()
        .execute(
            "SELECT t.id,t.name,w.name workspace_name FROM topics t JOIN workspaces w ON w.id=t.workspace_id WHERE w.user_id=? AND NOT EXISTS (SELECT 1 FROM content_states s WHERE s.content_id IN (w.id,t.id)) ORDER BY w.name,t.name",
            (g.user["id"],),
        )
        .fetchall(),
    }
