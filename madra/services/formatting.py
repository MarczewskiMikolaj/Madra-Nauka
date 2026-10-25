"""Safe Markdown rendering: raw HTML, images and unsafe URLs are disabled."""

import re

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from markupsafe import Markup

_parser = (
    MarkdownIt("commonmark", {"html": False, "breaks": True, "maxNesting": 20})
    .enable("table")
    .disable("image")
    .use(dollarmath_plugin, allow_labels=False)
)


def render_content(value):
    # Rendered HTML is generated solely by the trusted parser, never user HTML.
    return Markup(_parser.render(str(value or "")))


_SOLUTION_LABEL = (
    r"(?:rozwiązanie|odpowiedź|solution|answer|lösung|antwort|solución|respuesta)"
)
_NEXT_SECTION = re.compile(
    r"^\s*(?:\*\*|__)(?:kryterium przejścia|umiejętności do opanowania|ćwiczenie|zadanie|rozwiązany przykład)\b",
    re.IGNORECASE,
)


def render_note_content(value):
    """Collapse marked solutions, keeping raw HTML disabled and code untouched."""
    env = {}
    tokens = _parser.parse(str(value or ""), env)
    parts, start, solution_level = [], 0, None

    def render_until(end):
        parts.append(_parser.renderer.render(tokens[start:end], _parser.options, env))

    for i, token in enumerate(tokens):
        if token.level != 0 or token.type not in ("heading_open", "paragraph_open"):
            continue
        inline = tokens[i + 1]
        text = re.sub(r"\*\*|__", "", inline.content).strip()
        heading = token.type == "heading_open"
        is_solution = bool(
            re.match(
                r"^" + _SOLUTION_LABEL + (r"\s*:?$" if heading else r"\s*:"),
                text,
                re.IGNORECASE,
            )
        )
        ends_solution = solution_level is not None and (
            is_solution
            or (heading and int(token.tag[1:]) <= solution_level)
            or (not heading and _NEXT_SECTION.match(inline.content))
        )
        if ends_solution:
            render_until(i)
            parts.append("</div></details>")
            start, solution_level = i, None
        if is_solution:
            render_until(i)
            parts.append(
                '<details class="note-solution"><summary>Pokaż rozwiązanie</summary><div class="note-solution-content">'
            )
            start, solution_level = i, int(token.tag[1:]) if heading else 6
    render_until(len(tokens))
    if solution_level is not None:
        parts.append("</div></details>")
    return Markup("".join(parts))
