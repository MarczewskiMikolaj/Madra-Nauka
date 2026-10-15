"""Owned, bounded and repeat-safe exercise imports with preview."""

import csv
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
)
from .auth import login_required
from .db import get_db, transaction
from .library import owned_topic
from .services.exercises import validate_exercise, insert_exercise
from .services.learning import now_iso

bp = Blueprint("imports", __name__)


def parse_import(text, format):
    if not text.strip() or len(text.encode("utf-8")) > 1024 * 1024:
        raise ValueError("Wklej lub wgraj dane do 1 MB.")
    if format == "json":
        try:
            rows = json.loads(text)
        except (ValueError, RecursionError):
            raise ValueError("Nieprawidłowy JSON.") from None
    else:
        try:
            delimiter = (
                "\t"
                if format == "tsv"
                else csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
            )
        except csv.Error:
            delimiter = ","
        try:
            data = list(csv.reader(io.StringIO(text), delimiter=delimiter))
        except csv.Error:
            raise ValueError("Nieprawidłowy CSV/TSV.") from None
        data = [row for row in data if any(cell.strip() for cell in row)]
        if not data:
            raise ValueError("Brak ćwiczeń.")
        if "prompt" in data[0] and "answer" in data[0]:
            headers = [s.strip() for s in data[0]]
            if len(set(headers)) != len(headers):
                raise ValueError("Nagłówki muszą być różne.")
            if any(len(row) != len(headers) for row in data[1:]):
                raise ValueError("Każdy wiersz musi mieć tyle pól, ile nagłówków.")
            rows = [dict(zip(headers, row)) for row in data[1:]]
        else:
            if any(len(row) != 2 for row in data):
                raise ValueError(
                    "Bez nagłówków podaj dwie kolumny: pytanie i odpowiedź."
                )
            rows = [
                {"kind": "flashcard", "prompt": row[0], "answer": row[1]}
                for row in data
            ]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("Jednorazowo dodaj 1–200 ćwiczeń.")
    result = []
    for index, row in enumerate(rows, 1):
        try:
            result.append(validate_exercise(row))
        except ValueError as error:
            raise ValueError(f"Ćwiczenie {index}: {error}") from None
    return result


@bp.route("/tematy/<tid>/import-cwiczen", methods=["GET", "POST"])
@login_required
def upload(tid):
    topic = owned_topic(tid)
    if request.method == "POST":
        try:
            format = request.form.get("format", "tsv")
            if format not in ("json", "csv", "tsv", "auto"):
                raise ValueError("Wybierz JSON, CSV lub TSV.")
            text = request.form.get("text", "")
            file = request.files.get("file")
            if file and file.filename:
                data = file.read(1024 * 1024 + 1)
                if len(data) > 1024 * 1024:
                    raise ValueError("Plik jest za duży — limit 1 MB.")
                try:
                    text = data.decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise ValueError("Zapisz plik w UTF-8.") from None
            if format == "auto":
                format = (
                    "json"
                    if text.lstrip().startswith("[")
                    else "tsv" if "\t" in text else "csv"
                )
            items = parse_import(text, format)
            iid = uuid4().hex
            with transaction() as db:
                db.execute(
                    "INSERT INTO activity_imports VALUES (?,?,?,?,?,NULL)",
                    (
                        iid,
                        g.user["id"],
                        tid,
                        json.dumps(items, ensure_ascii=False),
                        now_iso(),
                    ),
                )
            return redirect(url_for("imports.preview", iid=iid))
        except ValueError as error:
            flash(str(error), "error")
            return (
                render_template("import_exercises.html", topic=topic, nav="library"),
                400,
            )
    return render_template("import_exercises.html", topic=topic, nav="library")


@bp.route("/importy/<iid>", methods=["GET", "POST"])
@login_required
def preview(iid):
    row = (
        get_db()
        .execute(
            "SELECT * FROM activity_imports WHERE id=? AND user_id=?",
            (iid, g.user["id"]),
        )
        .fetchone()
    )
    if not row:
        abort(404)
    topic = owned_topic(row["topic_id"])
    items = json.loads(row["payload_json"])
    if request.method == "POST":
        with transaction() as db:
            state = db.execute(
                "SELECT * FROM activity_imports WHERE id=? AND user_id=?",
                (iid, g.user["id"]),
            ).fetchone()
            if not state:
                abort(404)
            if not state["imported_at"]:
                for item in json.loads(state["payload_json"]):
                    insert_exercise(db, topic["id"], item)
                db.execute(
                    "UPDATE activity_imports SET imported_at=? WHERE id=?",
                    (now_iso(), iid),
                )
        flash("Ćwiczenia zostały dodane do tematu.", "success")
        return redirect(url_for("library.topic", tid=topic["id"]))
    return render_template(
        "import_preview.html", topic=topic, items=items, source=row, nav="library"
    )
