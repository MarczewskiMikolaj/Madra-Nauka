import io
import json
import zipfile
import unittest
import sqlite3
from pathlib import Path
from unittest.mock import patch
from xml.sax.saxutils import escape
import test_mvp
from madra.db import get_db, transaction
from madra.services.files import validate_file, inspect_file

TEXT = (
    "Fotosynteza jest procesem przekształcania energii świetlnej w energię chemiczną. "
    "Chlorofil pochłania światło wykorzystywane przez rośliny do wytwarzania związków organicznych. "
    "Mitochondria uczestniczą w oddychaniu komórkowym i produkcji ATP."
)


class UploadTests(unittest.TestCase):
    setUpClass = classmethod(test_mvp.MVPTests.setUpClass.__func__)
    setUp = test_mvp.MVPTests.setUp
    tearDown = test_mvp.MVPTests.tearDown
    authenticate = test_mvp.MVPTests.authenticate
    post = test_mvp.MVPTests.post
    count = test_mvp.MVPTests.count

    def test_migration_removes_extraction_preserves_original_and_ai(self):
        db = sqlite3.connect(":memory:")
        migrations = Path(__file__).parents[1] / "madra" / "migrations"
        for name in ["001_initial.sql", "002_uploads.sql", "003_ai_jobs.sql"]:
            db.executescript((migrations / name).read_text())
        db.execute("INSERT INTO users VALUES ('user','User','hash',0,'now')")
        for uid, value in [
            ("local", {"guide": "Fragment", "activities": []}),
            ("ai", {"generator": "ai", "guide": "AI", "activities": []}),
        ]:
            db.execute(
                "INSERT INTO uploads VALUES (?, 'user', NULL,NULL,'x.pdf', ?, 'transcription', ?, 'now', NULL)",
                (uid, b"original", json.dumps(value)),
            )
        db.commit()
        db.executescript((migrations / "004_original_files.sql").read_text())
        self.assertNotIn(
            "text_content", [row[1] for row in db.execute("PRAGMA table_info(uploads)")]
        )
        self.assertEqual(
            db.execute("SELECT file_blob FROM uploads WHERE id='local'").fetchone()[0],
            b"original",
        )
        self.assertEqual(
            json.loads(
                db.execute(
                    "SELECT draft_json FROM uploads WHERE id='local'"
                ).fetchone()[0]
            )["generator"],
            "pending",
        )
        self.assertEqual(
            json.loads(
                db.execute("SELECT draft_json FROM uploads WHERE id='ai'").fetchone()[0]
            )["guide"],
            "AI",
        )
        db.close()

    def upload(self, filename="biologia.txt", data=None):
        return self.post(
            "/materialy/wgraj",
            {
                "file": (io.BytesIO(data or TEXT.encode()), filename),
                "topic_id": self.tid,
            },
        )

    def save(self, location):
        uid = location.rsplit("/", 1)[-1]
        # Simulate a completed AI result; uploading alone produces no materials.
        with self.app.app_context(), transaction() as db:
            simulated = {
                "guide": "Fotosynteza zamienia energię świetlną w chemiczną.",
                "generator": "ai",
                "activities": [
                    {
                        "kind": "open",
                        "prompt": "Jaką przemianą jest fotosynteza?",
                        "answer": "Świetlnej w chemiczną.",
                        "label": "Tekst",
                        "minutes": 2,
                    },
                    {
                        "kind": "open",
                        "prompt": "Jaką rolę pełni chlorofil?",
                        "answer": "Pochłania światło.",
                        "label": "Tekst",
                        "minutes": 2,
                    },
                ],
            }
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?",
                (json.dumps(simulated), uid),
            )
            draft = json.loads(
                get_db()
                .execute("SELECT draft_json FROM uploads WHERE id=?", (uid,))
                .fetchone()[0]
            )
        data = {
            "title": "Procesy biologiczne",
            "guide": draft["guide"],
            "selected": ["0", "1"],
        }
        for i, item in enumerate(draft["activities"]):
            data[f"prompt_{i}"] = item["prompt"]
            data[f"answer_{i}"] = item["answer"]
        return self.post(location, data), data

    def test_upload_preview_edit_save_and_repeat(self):
        response = self.upload()
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.location)
        self.assertNotIn(TEXT.encode(), page.data)
        self.assertEqual(self.count("activities"), 0)
        self.assertNotIn(b'name="prompt_0"', page.data)
        self.assertNotIn(b'name="guide"', page.data)
        rejected = self.post(response.location, {"title": "Test", "guide": "Test"})
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.count("materials"), 0)
        saved, data = self.save(response.location)
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(self.count("materials"), 1)
        self.assertEqual(self.count("activities"), 2)
        self.post(response.location, data)
        self.assertEqual(self.count("activities"), 2)
        topic = self.client.get(saved.location)
        self.assertIn(b"biologia.txt", topic.data)
        self.assertEqual(
            self.client.get(response.location + "/pobierz").data, TEXT.encode()
        )

    def test_source_owner_is_enforced(self):
        response = self.upload()
        with self.client.session_transaction() as session:
            session.clear()
        self.post(
            "/konto/demo"
        )  # actual demo URL handled below by direct user creation
        with self.app.app_context():
            db = get_db()
            db.execute(
                "INSERT INTO users VALUES ('other','Other',?,0,'now')",
                (self.password_hash,),
            )
        self.authenticate(self.client, "other")
        for path in [response.location, response.location + "/pobierz"]:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.post(response.location, {}).status_code, 404)
        self.assertEqual(self.post(response.location + "/usun", {}).status_code, 404)

    def test_invalid_files_leave_no_draft(self):
        for name, data in [
            ("bad.exe", b"test"),
            ("bad.pdf", b"not pdf"),
            ("empty.txt", b"   "),
            ("binary.txt", b"\x00" * 100),
            ("bad.docx", b"broken"),
        ]:
            page = self.upload(name, data)
            self.assertEqual(page.status_code, 200)
        self.assertEqual(self.count("uploads"), 0)

    def test_docx_validation_without_text_preview(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
                + escape(TEXT)
                + "</w:t></w:r></w:p></w:body></w:document>",
            )
        response = self.upload("notatki.docx", data.getvalue())
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("Chlorofil".encode(), self.client.get(response.location).data)

    def test_blank_and_encrypted_pdf(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        data = io.BytesIO()
        writer.write(data)
        self.assertEqual(validate_file("scan.pdf", data.getvalue()), {"pages": 1})
        uploaded = self.upload("scan.pdf", data.getvalue())
        self.assertEqual(uploaded.status_code, 302)
        self.assertNotIn(b"source-preview", self.client.get(uploaded.location).data)
        writer.encrypt("secret")
        data = io.BytesIO()
        writer.write(data)
        with self.assertRaisesRegex(ValueError, "hasła"):
            validate_file("protected.pdf", data.getvalue())

    def test_text_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

        writer = PdfWriter()
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(
            b"BT /F1 12 Tf 40 700 Td (Photosynthesis converts light energy into chemical energy. Chlorophyll absorbs light for producing organic compounds in plants.) Tj ET"
        )
        page[NameObject("/Contents")] = writer._add_object(stream)
        data = io.BytesIO()
        writer.write(data)
        self.assertEqual(validate_file("biology.pdf", data.getvalue()), {"pages": 1})

    def test_discard_and_new_workspace(self):
        response = self.post(
            "/materialy/wgraj", {"file": (io.BytesIO(TEXT.encode()), "nowy.md")}
        )
        saved, _ = self.save(response.location)
        self.assertEqual(saved.status_code, 302)
        self.assertEqual(self.count("workspaces"), 2)
        self.assertEqual(self.count("topics"), 2)
        draft = self.upload()
        self.assertEqual(self.post(draft.location + "/usun").status_code, 302)
        self.assertEqual(self.client.get(draft.location).status_code, 404)

    def test_limits_and_csrf(self):
        response = self.client.post(
            "/materialy/wgraj", data={"file": (io.BytesIO(TEXT.encode()), "x.txt")}
        )
        self.assertEqual(response.status_code, 400)
        with self.assertRaises(ValueError):
            validate_file("huge.txt", b"x" * (10 * 1024 * 1024 + 1))
        self.assertEqual(inspect_file(".txt", b"x" * 150001), {})
        with patch(
            "madra.services.files.subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired("parse", 20),
        ):
            with self.assertRaisesRegex(ValueError, "długo"):
                validate_file("x.txt", TEXT.encode())
