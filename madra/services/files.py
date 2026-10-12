"""Bounded file validation. No text extraction or local material generation."""

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def validate_file(filename, data):
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError("Wybierz PDF, DOCX, TXT lub MD.")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Plik musi mieć od 1 bajtu do 10 MB.")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "madra.services.files", suffix],
            input=data,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValueError(
            "Sprawdzanie trwało zbyt długo. Podziel plik na części."
        ) from None
    if result.returncode:
        raise ValueError("Nie udało się sprawdzić pliku. Sprawdź jego format.")
    payload = json.loads(result.stdout)
    if payload.get("error"):
        raise ValueError(payload["error"])
    return payload["metadata"]


def inspect_file(suffix, data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Plik musi mieć od 1 bajtu do 10 MB.")
    if suffix == ".pdf":
        from pypdf import PdfReader

        if not data.startswith(b"%PDF-"):
            raise ValueError("Ten plik nie jest poprawnym PDF.")
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("PDF jest zabezpieczony. Wgraj wersję bez hasła.")
        pages = len(reader.pages)
        if not 1 <= pages <= 100:
            raise ValueError(
                "PDF musi mieć od 1 do 100 stron. Podziel duży plik na części."
            )
        return {"pages": pages}
    if suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 2 * 1024 * 1024:
                raise ValueError(
                    "Struktura dokumentu jest za duża. Podziel go na części."
                )
            xml = archive.read(info)
            if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                raise ValueError("Niedozwolona struktura dokumentu.")
            root = ElementTree.fromstring(xml)
            if (
                root.tag
                != "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document"
            ):
                raise ValueError("Nieprawidłowy dokument DOCX.")
        return {}
    if suffix not in {".txt", ".md"}:
        raise ValueError("Wybierz PDF, DOCX, TXT lub MD.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("Zapisz plik tekstowy w kodowaniu UTF-8.") from None
    if "\x00" in text or not text.strip():
        raise ValueError("Plik tekstowy jest pusty lub zawiera dane binarne.")
    return {}


if __name__ == "__main__":
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        if sys.platform == "linux":
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        value = {
            "metadata": inspect_file(sys.argv[1], sys.stdin.buffer.read(MAX_BYTES + 1))
        }
    except Exception as error:
        value = {
            "error": (
                str(error)
                if isinstance(error, ValueError)
                else "Uszkodzony lub nieobsługiwany dokument."
            )
        }
    print(json.dumps(value, ensure_ascii=False))
