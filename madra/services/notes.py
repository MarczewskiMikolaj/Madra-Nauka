"""Chapter storage and lossless presentation of both new and legacy notes."""

import re

from markdown_it import MarkdownIt


def _headings(content):
    """Read Markdown headings, excluding examples inside fenced code blocks."""
    offsets = [0]
    for line in content.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    tokens = MarkdownIt("commonmark").parse(content)
    return [
        {
            "start": offsets[token.map[0]],
            "end": offsets[token.map[1]],
            "level": int(token.tag[1:]),
            "title": tokens[i + 1].content.strip(),
        }
        for i, token in enumerate(tokens)
        if token.type == "heading_open"
    ]


def _chapter_body(content):
    """Reserve level two for chapter titles when serializing AI chapter objects."""
    content = content.strip().replace("\r\n", "\n").replace("\r", "\n")
    headings = _headings(content)
    if not headings:
        return content
    shift = max(0, 3 - min(h["level"] for h in headings))
    for heading in reversed(headings):
        level = min(6, heading["level"] + shift)
        content = (
            content[: heading["start"]]
            + "#" * level
            + " "
            + heading["title"]
            + "\n"
            + content[heading["end"] :]
        )
    return content


def chapter_guide(chapters, learning_order=None):
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 20:
        raise ValueError("AI zwróciło nieprawidłowe rozdziały notatki.")
    if learning_order is not None:
        if (
            not isinstance(learning_order, list)
            or any(type(i) is not int for i in learning_order)
            or sorted(learning_order) != list(range(1, len(chapters) + 1))
        ):
            raise ValueError("Plan nauki musi zawierać każdy rozdział dokładnie raz.")
        chapters = [chapters[i - 1] for i in learning_order]
    parts = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("AI zwróciło nieprawidłowy rozdział notatki.")
        title, content = chapter.get("title"), chapter.get("content")
        if (
            not isinstance(title, str)
            or not 1 <= len(title.strip()) <= 150
            or "\n" in title
            or "\r" in title
            or not isinstance(content, str)
            or not content.strip()
        ):
            raise ValueError("Rozdział notatki wymaga tytułu i treści.")
        parts.append("## " + title.strip() + "\n\n" + _chapter_body(content))
    guide = "\n\n".join(parts)
    if len(guide) > 50000:
        raise ValueError("Notatka AI jest za długa.")
    return guide


def content_title(content):
    """Use an existing heading or opening sentence, without inventing a topic."""
    for line in content.splitlines():
        line = re.sub(r"^\s*(?:#{1,6}\s*|[-*•]\s+|\d+[.)]\s+)", "", line).strip()
        if not line or re.fullmatch(
            r"(?:część|rozdział|sekcja)\s+\d+\.?", line, re.IGNORECASE
        ):
            continue
        title = re.split(r"(?<=[.!?])\s+", line, maxsplit=1)[0].rstrip(".!?")
        if len(title) > 90:
            title = title[:87].rsplit(" ", 1)[0].rstrip(",;:") + "…"
        return title
    return "Notatka"


def note_chapters(content):
    """Explicit headings take precedence; older plain notes split at paragraph boundaries."""
    content = str(content or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    headings = _headings(content)
    if headings:
        level = min(h["level"] for h in headings)
        headings = [h for h in headings if h["level"] == level]
        # Older AI drafts serialized chapter titles and their subheadings at the
        # same level. An empty parent belongs with its following content, rather
        # than becoming a blank accordion. Preserve every following section.
        empty_parents = [
            h
            for i, h in enumerate(headings[:-1])
            if not content[h["end"] : headings[i + 1]["start"]].strip()
        ]
        if empty_parents:
            # Consecutive empty headings are nested outlines, not blank cards.
            empty_starts = {h["start"] for h in empty_parents}
            empty_parents = [
                h
                for i, h in enumerate(headings)
                if h["start"] in empty_starts
                and (i == 0 or headings[i - 1]["start"] not in empty_starts)
            ]
            first = empty_parents[0]["start"]
            headings = [h for h in headings if h["start"] < first] + empty_parents
        chapters = []
        intro = content[: headings[0]["start"]].strip()
        if intro:
            chapters.append({"title": content_title(intro), "content": intro})
        for i, heading in enumerate(headings):
            end = headings[i + 1]["start"] if i + 1 < len(headings) else len(content)
            body = content[heading["end"] : end].strip()
            title = heading["title"]
            if re.fullmatch(
                r"(?:część|rozdział|sekcja)\s+\d+\.?", title, re.IGNORECASE
            ):
                title = content_title(body)
            chapters.append({"title": title, "content": body})
        # The previous generator stored its computed navigation as a chapter.
        # Navigation now belongs to the reader, outside numbered note content.
        return [
            chapter
            for chapter in chapters
            if not (
                chapter["title"] == "Plan nauki"
                and chapter["content"].startswith("Czytaj rozdziały w tej kolejności:")
            )
        ] or [{"title": "Notatka", "content": content}]
    parts, current = [], []
    for paragraph in re.split(r"\n\s*\n", content):
        if current and sum(len(p) for p in current) + len(paragraph) > 2500:
            parts.append("\n\n".join(current))
            current = []
        current.append(paragraph)
    if current:
        parts.append("\n\n".join(current))
    return [{"title": content_title(part), "content": part} for part in parts]
