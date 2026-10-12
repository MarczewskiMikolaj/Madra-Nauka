import json
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4
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
)
from .auth import login_required
from .db import get_db, transaction
from .uploads import owned_upload
from .services import chatgpt
from .services.ai_materials import FIXED_MODEL, generate
from .services.learning import now_iso

bp = Blueprint("ai", __name__)


def connection_info(uid):
    try:
        record = chatgpt.load(uid)
        return {
            "connected": chatgpt.permitted(record),
            "email": record.get("email", ""),
            "usage_consent": chatgpt.usage_consent(record),
        }
    except ValueError:
        return {"connected": False, "email": "", "usage_consent": False}


def local_only():
    if not current_app.config["CHATGPT_LOCAL_AUTH"] or request.remote_addr not in (
        "127.0.0.1",
        "::1",
    ):
        abort(403)


@bp.get("/konto/ai")
@login_required
def settings():
    info = connection_info(g.user["id"])
    choices = []
    if info["connected"]:
        try:
            choices = chatgpt.models(g.user["id"])
        except ValueError as error:
            flash(str(error), "error")
    return render_template(
        "ai_settings.html",
        info=info,
        models=choices,
        local_auth=current_app.config["CHATGPT_LOCAL_AUTH"],
        nav="ai",
    )


@bp.post("/konto/ai/polacz")
@login_required
def connect():
    local_only()
    if request.form.get("usage_consent") != "yes":
        flash(
            "Zaznacz zgodę na używanie puli Codex / ChatGPT Work i dostępnych kredytów, aby połączyć AI.",
            "error",
        )
        return redirect(url_for("ai.settings"))
    chatgpt.set_usage_consent(g.user["id"], True)
    return redirect(
        chatgpt.begin(g.user["id"], current_app.config["CHATGPT_CALLBACK_URL"])
    )


@bp.post("/konto/ai/zgoda")
@login_required
def update_usage_consent():
    local_only()
    allowed = request.form.get("usage_consent") == "yes"
    chatgpt.set_usage_consent(g.user["id"], allowed)
    flash(
        (
            "Zapisano zgodę na korzystanie z puli i dostępnych kredytów."
            if allowed
            else "Wycofano zgodę. Nowe generowanie jest zablokowane; już wysłane zadania mogą nadal zużywać pulę lub kredyty."
        ),
        "success",
    )
    return redirect(url_for("ai.settings"))


@bp.get("/auth/callback")
@login_required
def callback():
    local_only()
    try:
        record = chatgpt.finish(g.user["id"], request.args)
        if chatgpt.permitted(record):
            flash(
                "ChatGPT połączony. Możesz opracować pliki z użyciem swojego planu.",
                "success",
            )
        else:
            flash(
                "Zalogowano do ChatGPT, ale nie udzielono zgody na użycie planu. Połącz ponownie i zaznacz tę zgodę.",
                "error",
            )
    except ValueError as error:
        flash(str(error), "error")
    return redirect(url_for("ai.settings"))


@bp.post("/konto/ai/odlacz")
@login_required
def disconnect():
    confirmed = chatgpt.disconnect(g.user["id"])
    flash(
        (
            "Odłączono ChatGPT."
            if confirmed
            else "Odłączono lokalnie. Nie potwierdzono odwołania zgody w OpenAI; odłącz aplikację również w ustawieniach ChatGPT."
        ),
        "success" if confirmed else "error",
    )
    return redirect(url_for("ai.settings"))


def run_job(app, job_id, uid, upload_id, model, goal):
    with app.app_context():
        started = time.monotonic()
        last_stage = None

        def progress(stage, output_chars):
            nonlocal last_stage
            with transaction() as db:
                db.execute(
                    "UPDATE ai_jobs SET progress_json=? WHERE id=? AND state='running'",
                    (
                        json.dumps(
                            {
                                "stage": stage,
                                "output_chars": output_chars,
                                "updated_at": now_iso(),
                            }
                        ),
                        job_id,
                    ),
                )
            if stage != last_stage:
                app.logger.info(
                    "AI job=%s stage=%s output_chars=%s elapsed_s=%s",
                    job_id,
                    stage,
                    output_chars,
                    int(time.monotonic() - started),
                )
                last_stage = stage

        try:
            if not chatgpt.usage_consent(chatgpt.load(uid)):
                raise ValueError(
                    "Brak zgody na używanie puli i dostępnych kredytów. Udziel zgody w Połączeniu AI."
                )
            source = (
                get_db()
                .execute(
                    "SELECT filename,file_blob,imported_at FROM uploads WHERE id=? AND user_id=?",
                    (upload_id, uid),
                )
                .fetchone()
            )
            if not source or source["imported_at"]:
                raise ValueError("Plik nie jest dostępny do opracowania.")
            draft = generate(
                uid,
                source["filename"],
                source["file_blob"],
                model,
                goal,
                on_progress=progress,
            )
            draft["model"] = model
            draft["goal"] = goal
            with transaction() as db:
                source = db.execute(
                    "SELECT imported_at FROM uploads WHERE id=? AND user_id=?",
                    (upload_id, uid),
                ).fetchone()
                job = db.execute(
                    "SELECT state FROM ai_jobs WHERE id=?", (job_id,)
                ).fetchone()
                if (
                    not source
                    or source["imported_at"]
                    or not job
                    or job["state"] != "running"
                ):
                    raise ValueError(
                        "Plik został już zapisany lub generowanie wygasło. Wynik nie zastąpił materiałów."
                    )
                db.execute(
                    "UPDATE uploads SET draft_json=? WHERE id=? AND user_id=?",
                    (json.dumps(draft, ensure_ascii=False), upload_id, uid),
                )
                db.execute(
                    "UPDATE ai_jobs SET state='completed',finished_at=? WHERE id=?",
                    (now_iso(), job_id),
                )
            app.logger.info(
                "AI job=%s completed elapsed_s=%s",
                job_id,
                int(time.monotonic() - started),
            )
        except Exception as error:
            app.logger.warning(
                "AI job=%s failed stage=%s error_type=%s elapsed_s=%s",
                job_id,
                last_stage,
                type(error).__name__,
                int(time.monotonic() - started),
            )
            message = (
                str(error)[:500]
                if isinstance(error, ValueError)
                else "Generowanie nie powiodło się. Spróbuj ponownie."
            )
            with transaction() as db:
                db.execute(
                    "UPDATE ai_jobs SET state='failed',error=?,finished_at=? WHERE id=?",
                    (message, now_iso(), job_id),
                )


@bp.post("/pliki/<uid>/generuj-ai")
@login_required
def generate_materials(uid):
    source = owned_upload(uid)
    if source["imported_at"]:
        flash(
            "Ten zestaw został już zapisany. Wgraj plik ponownie, aby utworzyć nowe opracowanie.",
            "error",
        )
        return redirect(url_for("uploads.preview", uid=uid))
    try:
        info = connection_info(g.user["id"])
        if not info["connected"]:
            return redirect(url_for("ai.settings"))
        if not info["usage_consent"]:
            flash(
                "Najpierw udziel zgody na używanie puli Codex / ChatGPT Work i dostępnych kredytów.",
                "error",
            )
            return redirect(url_for("ai.settings"))
        choices = chatgpt.models(g.user["id"])
        model = FIXED_MODEL
        if model not in {m["id"] for m in choices}:
            raise ValueError(
                "GPT-5.6 Terra nie jest dostępny dla tego połączenia ChatGPT. Nie uruchomiono generowania."
            )
        goal = (
            request.form.get("goal", "").strip()[:1000]
            or "Zrozumienie materiału i przygotowanie do sprawdzianu."
        )
        jid = uuid4().hex
        with transaction() as db:
            running = db.execute(
                "SELECT id FROM ai_jobs WHERE upload_id=? AND state='running'", (uid,)
            ).fetchone()
            if running:
                return redirect(url_for("ai.job", jid=running["id"]))
            if (
                db.execute(
                    "SELECT COUNT(*) FROM ai_jobs WHERE user_id=? AND state='running'",
                    (g.user["id"],),
                ).fetchone()[0]
                >= 2
            ):
                raise ValueError("Poczekaj na ukończenie poprzednich opracowań.")
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,error,created_at,finished_at) VALUES (?,?,?,'running',?,?,'',?,NULL)",
                (jid, uid, g.user["id"], model, goal, now_iso()),
            )
        thread = threading.Thread(
            target=run_job,
            args=(
                current_app._get_current_object(),
                jid,
                g.user["id"],
                uid,
                model,
                goal,
            ),
            daemon=True,
        )
        thread.start()
        return redirect(url_for("ai.job", jid=jid))
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("uploads.preview", uid=uid))


@bp.get("/ai/zadania/<jid>")
@login_required
def job(jid):
    row = (
        get_db()
        .execute("SELECT * FROM ai_jobs WHERE id=? AND user_id=?", (jid, g.user["id"]))
        .fetchone()
    )
    if not row:
        abort(404)
    if row["state"] == "completed":
        return redirect(url_for("uploads.preview", uid=row["upload_id"]))
    progress = json.loads(row["progress_json"])
    elapsed = max(
        0,
        int(
            (
                datetime.now(timezone.utc) - datetime.fromisoformat(row["created_at"])
            ).total_seconds()
        ),
    )
    return render_template(
        "ai_job.html",
        job=row,
        progress=progress,
        elapsed=f"{elapsed // 60} min {elapsed % 60} s",
        nav="library",
    )


def init_app(app):
    # Threads do not survive server restart. Preserve drafts and make retry possible.
    with app.app_context(), transaction() as db:
        db.execute(
            "UPDATE ai_jobs SET state='failed',error='Serwer został uruchomiony ponownie. Spróbuj ponownie.',finished_at=? WHERE state='running'",
            (now_iso(),),
        )
