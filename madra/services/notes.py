"""Chapter storage and lossless presentation of both new and legacy notes."""

import re


def chapter_guide(chapters):
    if not isinstance(chapters, list) or not 1 <= len(chapters) <= 20:
        raise ValueError("AI zwróciło nieprawidłowe rozdziały notatki.")
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
        parts.append("## " + title.strip() + "\n\n" + content.strip())
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
    content = str(content or "").strip()
    headings = list(re.finditer(r"(?m)^#{1,3} ([^\n]+)\n", content + "\n"))
    if headings:
        chapters = []
        intro = content[: headings[0].start()].strip()
        if intro:
            chapters.append({"title": content_title(intro), "content": intro})
        for i, heading in enumerate(headings):
            end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
            body = content[heading.end() : end].strip()
            title = heading.group(1).strip()
            if re.fullmatch(
                r"(?:część|rozdział|sekcja)\s+\d+\.?", title, re.IGNORECASE
            ):
                title = content_title(body)
            chapters.append({"title": title, "content": body})
        return chapters
    parts, current = [], []
    for paragraph in re.split(r"\n\s*\n", content):
        if current and sum(len(p) for p in current) + len(paragraph) > 2500:
            parts.append("\n\n".join(current))
            current = []
        current.append(paragraph)
    if current:
        parts.append("\n\n".join(current))
    return [{"title": content_title(part), "content": part} for part in parts]
