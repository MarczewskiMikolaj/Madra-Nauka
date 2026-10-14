"""Validated exercise content shared by manual editing, imports and AI."""

import json
from uuid import uuid4
from .learning import KINDS, KIND_DIMENSION, now_iso


def validate_exercise(value):
    if not isinstance(value, dict):
        raise ValueError("Każde ćwiczenie musi być obiektem.")
    kind = value.get("kind", "flashcard")
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("Wybierz jeden z pięciu rodzajów ćwiczenia.")
    result = {"kind": kind}
    for field, limit in [("prompt", 10000), ("answer", 10000)]:
        text = value.get(field, "")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= limit:
            raise ValueError("Polecenie i odpowiedź muszą mieć 1–10000 znaków.")
        result[field] = text.strip()
    try:
        raw = value.get("minutes", 2)
        if isinstance(raw, (bool, float)):
            raise ValueError()
        minutes = int(2 if raw in (None, "") else raw)
    except (ValueError, TypeError):
        raise ValueError("Czas ćwiczenia musi wynosić 1–15 minut.") from None
    if not 1 <= minutes <= 15:
        raise ValueError("Czas ćwiczenia musi wynosić 1–15 minut.")
    result["minutes"] = minutes
    options = value.get("options", [])
    if isinstance(options, str):
        options = [s.strip() for s in options.split("|") if s.strip()]
    if kind == "quiz" and (
        not isinstance(options, list)
        or not 2 <= len(options) <= 6
        or any(
            not isinstance(s, str) or not s.strip() or len(s) > 1000 for s in options
        )
        or len(set(options)) != len(options)
        or result["answer"] not in options
    ):
        raise ValueError(
            "Quiz wymaga 2–6 różnych opcji i odpowiedzi zgodnej z jedną opcją."
        )
    if kind == "cloze" and "[...]" not in result["prompt"]:
        raise ValueError("Luka musi zawierać [...].")
    result["options"] = options if kind == "quiz" else []
    hints = value.get("hints") or []
    if isinstance(hints, str):
        hints = [s.strip() for s in hints.split("|") if s.strip()]
    if (
        not isinstance(hints, list)
        or len(hints) > 3
        or any(not isinstance(s, str) or len(s) > 2000 for s in hints)
    ):
        raise ValueError("Dodaj maksymalnie 3 podpowiedzi po 2000 znaków.")
    result["hints"] = [hint.strip() for hint in hints if hint.strip()]
    for field, limit in [("explanation", 10000), ("rubric", 4000)]:
        text = value.get(field) or ""
        if not isinstance(text, str) or len(text) > limit:
            raise ValueError("Wyjaśnienie lub kryteria oceny są za długie.")
        result[field] = text.strip()
    return result


def save_support(db, aid, item, material_id=None, chapter=0):
    db.execute(
        "INSERT INTO activity_support VALUES (?,?,?,?,?,?) ON CONFLICT(activity_id) DO UPDATE SET hints_json=excluded.hints_json,explanation=excluded.explanation,rubric=excluded.rubric,material_id=excluded.material_id,source_chapter=excluded.source_chapter",
        (
            aid,
            json.dumps(item.get("hints", []), ensure_ascii=False),
            item.get("explanation", ""),
            item.get("rubric", ""),
            material_id,
            chapter,
        ),
    )


def insert_exercise(db, tid, item):
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
    return aid
