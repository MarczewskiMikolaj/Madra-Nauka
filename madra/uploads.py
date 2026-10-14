import io
import json
from pathlib import Path
from uuid import uuid4
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from .auth import login_required
from .db import get_db, transaction
from .library import owned_topic, owned_workspace, required_text
from .services.files import MAX_BYTES, validate_file
from .services.ai_materials import FIXED_MODEL
from .services.learning import KIND_DIMENSION, now_iso
from .services.exercises import save_support
from .services.notes import note_chapters

bp = Blueprint("uploads", __name__)


def owned_upload(uid):
    row = (
        get_db()
        .execute("SELECT * FROM uploads WHERE id=? AND user_id=?", (uid, g.user["id"]))
        .fetchone()
    )
    if not row:
        abort(404)
    return row


@bp.route("/materialy/wgraj", methods=["GET", "POST"])
@login_required
def upload():
    tid = request.args.get("topic_id") or request.form.get("topic_id")
    topic = owned_topic(tid) if tid else None
    spaces = (
        get_db()
        .execute(
            "SELECT * FROM workspaces WHERE user_id=? ORDER BY name", (g.user["id"],)
        )
        .fetchall()
    )
    if request.method == "POST":
        try:
            file = request.files.get("file")
            if not file or not file.filename:
                raise ValueError("Wybierz plik do wgrania.")
            filename = file.filename.replace("\\", "/").rsplit("/", 1)[-1][:200]
            filename = "".join(c for c in filename if c.isprintable()) or "material.txt"
            wid = (
                topic["workspace_id"]
                if topic
                else request.form.get("workspace_id") or None
            )
            if wid:
                owned_workspace(wid)
            data = file.read(MAX_BYTES + 1)
            metadata = validate_file(filename, data)
            draft = {
                "guide": "",
                "activities": [],
                "generator": "pending",
                "file_metadata": metadata,
            }
            uid = uuid4().hex
            with transaction() as db:
                db.execute(
                    "INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?,NULL)",
                    (
                        uid,
                        g.user["id"],
                        wid,
                        tid,
                        filename,
                        data,
                        json.dumps(draft, ensure_ascii=False),
                        now_iso(),
                    ),
                )
            return redirect(url_for("uploads.preview", uid=uid))
        except ValueError as error:
            flash(str(error), "error")
    return render_template("upload.html", topic=topic, spaces=spaces, nav="library")


@bp.route("/pliki/<uid>", methods=["GET", "POST"])
@login_required
def preview(uid):
    source = owned_upload(uid)
    draft = json.loads(source["draft_json"])
    running = (
        get_db()
        .execute("SELECT id FROM ai_jobs WHERE upload_id=? AND state='running'", (uid,))
        .fetchone()
    )
    last_job = (
        get_db()
        .execute(
            "SELECT id,state,error FROM ai_jobs WHERE upload_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1",
            (uid, g.user["id"]),
        )
        .fetchone()
    )
    if request.method == "POST":
        if running:
            abort(409)
        if source["imported_at"]:
            return redirect(url_for("library.topic", tid=source["topic_id"]))
        try:
            if draft.get("generator") == "pending":
                raise ValueError("Najpierw przygotuj notatkę i ćwiczenia z AI.")
            title = required_text("title", "Nazwa tematu", 150)
            guide = required_text("guide", "Notatka", 50000)
            chosen = set(request.form.getlist("selected"))
            items = []
            for i, item in enumerate(draft["activities"]):
                if str(i) in chosen:
                    prompt = required_text(f"prompt_{i}", "Polecenie", 10000)
                    answer = required_text(f"answer_{i}", "Odpowiedź", 10000)
                    if item["kind"] == "cloze" and "[...]" not in prompt:
                        raise ValueError("Ćwiczenie z luką musi zawierać [...].")
                    options = (
                        [
                            x.strip()
                            for x in request.form.get(f"options_{i}", "").splitlines()
                            if x.strip()
                        ]
                        if item["kind"] == "quiz"
                        else []
                    )
                    if item["kind"] == "quiz" and (
                        not 2 <= len(options) <= 6
                        or len(set(options)) != len(options)
                        or answer not in options
                        or any(len(x) > 1000 for x in options)
                    ):
                        raise ValueError(
                            "Quiz wymaga 2–6 różnych wariantów, a odpowiedź musi być jednym z nich."
                        )
                    items.append(
                        {
                            **item,
                            "prompt": prompt,
                            "answer": answer,
                            "options": options,
                            "explanation": request.form.get(
                                f"explanation_{i}", item.get("explanation", "")
                            ),
                            "rubric": request.form.get(
                                f"rubric_{i}", item.get("rubric", "")
                            ),
                        }
                    )
            from .services.exercises import validate_exercise

            items = [{**item, **validate_exercise(item)} for item in items]
            with transaction() as db:
                # Check again under the write lock; repeat submits must not duplicate content.
                state = db.execute(
                    "SELECT imported_at,topic_id FROM uploads WHERE id=?", (uid,)
                ).fetchone()
                if state["imported_at"]:
                    tid = state["topic_id"]
                else:
                    wid = source["workspace_id"]
                    tid = source["topic_id"]
                    if not wid:
                        wid = uuid4().hex
                        db.execute(
                            "INSERT INTO workspaces VALUES (?,?,?,?,?,?,NULL)",
                            (
                                wid,
                                g.user["id"],
                                title,
                                "Materiały z wgranego pliku",
                                "blue",
                                now_iso(),
                            ),
                        )
                    if not tid:
                        tid = uuid4().hex
                        db.execute(
                            "INSERT INTO topics VALUES (?,?,?,?,?)",
                            (tid, wid, title, "", now_iso()),
                        )
                    for name, content in [(title, guide)]:
                        mid = uuid4().hex
                        db.execute(
                            "INSERT INTO materials VALUES (?,?,?,?,?,?,?)",
                            (mid, tid, "note", name, content, now_iso(), now_iso()),
                        )
                        db.execute(
                            "INSERT INTO upload_materials VALUES (?,?)", (uid, mid)
                        )
                    for item in items:
                        aid = uuid4().hex
                        db.execute(
                            "INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,0,NULL,?,?)",
                            (
                                aid,
                                tid,
                                item["kind"],
                                KIND_DIMENSION[item["kind"]],
                                item["prompt"],
                                item["answer"],
                                json.dumps(item.get("options", []), ensure_ascii=False),
                                item["minutes"],
                                now_iso(),
                                now_iso(),
                            ),
                        )
                        save_support(db, aid, item)
                        db.execute(
                            "INSERT INTO upload_activities VALUES (?,?,?)",
                            (uid, aid, item["label"]),
                        )
                    db.execute(
                        "UPDATE uploads SET workspace_id=?,topic_id=?,imported_at=? WHERE id=?",
                        (wid, tid, now_iso(), uid),
                    )
            flash(
                "Materiały i wybrane ćwiczenia są gotowe. Możesz rozpocząć naukę.",
                "success",
            )
            return redirect(url_for("library.topic", tid=tid))
        except ValueError as error:
            flash(str(error), "error")
    from .ai import connection_info
    from .services import chatgpt

    info = connection_info(g.user["id"])
    models = []
    if info["connected"] and not source["imported_at"] and not running:
        try:
            models = [
                model
                for model in chatgpt.models(g.user["id"])
                if model["id"] == FIXED_MODEL
            ]
        except ValueError as error:
            flash(str(error), "error")
    return render_template(
        "upload_preview.html",
        info=info,
        models=models,
        running=running,
        last_job=last_job,
        source=source,
        saved_notes=(
            get_db()
            .execute(
                "SELECT m.* FROM materials m JOIN upload_materials um ON um.material_id=m.id WHERE um.upload_id=?",
                (uid,),
            )
            .fetchall()
            if source["imported_at"]
            else []
        ),
        draft=draft,
        title=draft.get("title") or Path(source["filename"]).stem[:150],
        nav="library",
    )


@bp.get("/pliki/<uid>/pobierz")
@login_required
def download(uid):
    source = owned_upload(uid)
    return send_file(
        io.BytesIO(source["file_blob"]),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=source["filename"],
    )


@bp.post("/pliki/<uid>/usun")
@login_required
def discard(uid):
    source = owned_upload(uid)
    if (
        source["imported_at"]
        or get_db()
        .execute("SELECT 1 FROM ai_jobs WHERE upload_id=? AND state='running'", (uid,))
        .fetchone()
    ):
        abort(409)
    with transaction() as db:
        db.execute("DELETE FROM ai_jobs WHERE upload_id=?", (uid,))
        db.execute("DELETE FROM uploads WHERE id=? AND user_id=?", (uid, g.user["id"]))
    flash("Usunięto plik i niezapisane propozycje.", "success")
    return redirect(url_for("library.index"))


@bp.get("/pliki/<uid>/czytaj")
@login_required
def view_original(uid):
    source = owned_upload(uid)
    pdf = source["filename"].lower().endswith(".pdf")
    return send_file(
        io.BytesIO(source["file_blob"]),
        mimetype="application/pdf" if pdf else "application/octet-stream",
        as_attachment=not pdf,
        download_name=source["filename"],
    )


@bp.post("/pliki/<uid>/rozbuduj")
@login_required
def expand(uid):
    source = owned_upload(uid)
    if not source["imported_at"]:
        abort(409)
    try:
        mid = request.form.get("material_id", "")
        note = (
            get_db()
            .execute(
                "SELECT m.* FROM materials m JOIN upload_materials um ON um.material_id=m.id WHERE um.upload_id=? AND m.id=?",
                (uid, mid),
            )
            .fetchone()
        )
        if not note:
            raise ValueError("Wybierz notatkę z tego opracowania.")
        chapters = note_chapters(note["content"])
        chapter = int(request.form.get("chapter", "0"))
        if not 1 <= chapter <= len(chapters):
            raise ValueError("Wybierz poprawny rozdział.")
        focus = chapters[chapter - 1]["title"]
        nid = uuid4().hex
        draft = {
            "guide": "",
            "activities": [],
            "generator": "pending",
            "parent_upload_id": uid,
            "focus": focus,
            "goal": "Przygotuj dodatkowe ćwiczenia i wyjaśnienia do zagadnienia: "
            + focus
            + ". Analizuj cały oryginał, skupiając ćwiczenia na tym rozdziale.",
            "file_metadata": json.loads(source["draft_json"]).get("file_metadata", {}),
        }
        with transaction() as db:
            existing = db.execute(
                "SELECT id FROM uploads WHERE user_id=? AND imported_at IS NULL AND json_extract(draft_json,'$.parent_upload_id')=? AND json_extract(draft_json,'$.focus')=? ORDER BY created_at LIMIT 1",
                (g.user["id"], uid, focus),
            ).fetchone()
            if existing:
                return redirect(url_for("uploads.preview", uid=existing["id"]))
            db.execute(
                "INSERT INTO uploads VALUES (?,?,?,?,?,?,?,?,NULL)",
                (
                    nid,
                    g.user["id"],
                    source["workspace_id"],
                    source["topic_id"],
                    source["filename"],
                    source["file_blob"],
                    json.dumps(draft, ensure_ascii=False),
                    now_iso(),
                ),
            )
        flash(
            "Oryginał jest gotowy do kolejnego opracowania. Uruchom AI, aby wysłać plik i cel. Dotychczasowe materiały pozostają zachowane.",
            "success",
        )
        return redirect(url_for("uploads.preview", uid=nid))
    except (ValueError, TypeError):
        flash("Wybierz notatkę i poprawny numer rozdziału.", "error")
        return redirect(url_for("uploads.preview", uid=uid))
