"""Account changes, private images, migration and session invalidation."""

import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from madra import create_app
from madra.db import get_db
from werkzeug.security import check_password_hash


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database = str(Path(self.directory.name) / "test.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE": self.database,
                "CLOUD_STATE_BUCKET": None,
            }
        )
        self.client = self.app.test_client()
        self.register(self.client, "Alice")

    def tearDown(self):
        self.directory.cleanup()

    def post(self, client, path, data=None, follow=False):
        with client.session_transaction() as session:
            session.setdefault("csrf", "test-token")
            token = session["csrf"]
        return client.post(
            path, data={"csrf_token": token, **(data or {})}, follow_redirects=follow
        )

    def register(self, client, username):
        return self.post(
            client,
            "/register",
            {
                "username": username,
                "email": username.casefold() + "@example.test",
                "password": "old-password-123",
                "confirm_password": "old-password-123",
            },
        )

    def user(self):
        with self.app.app_context():
            return dict(
                get_db()
                .execute("SELECT * FROM users WHERE username='Alice'")
                .fetchone()
            )

    @staticmethod
    def image(format="PNG"):
        data = io.BytesIO()
        Image.new("RGB", (400, 300), "blue").save(data, format=format)
        data.seek(0)
        return data

    def test_rename_preserves_id_and_changes_login(self):
        uid = self.user()["id"]
        response = self.post(
            self.client, "/konto/profil", {"username": " Nowa nazwa "}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Nowa nazwa", response.data)
        with self.app.app_context():
            self.assertEqual(
                get_db()
                .execute("SELECT username FROM users WHERE id=?", (uid,))
                .fetchone()[0],
                "Nowa nazwa",
            )
        self.post(self.client, "/logout")
        self.assertEqual(
            self.post(
                self.client,
                "/login",
                {"username": "Alice", "password": "old-password-123"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                self.client,
                "/login",
                {"username": "Nowa nazwa", "password": "old-password-123"},
            ).status_code,
            302,
        )

    def test_conflicting_invalid_names_and_csrf(self):
        other = self.app.test_client()
        self.register(other, "Bob")
        for name in ("bob", "a", "<script>", "x" * 41, ""):
            self.assertEqual(
                self.post(self.client, "/konto/profil", {"username": name}).status_code,
                400,
            )
        for path in ("/konto/profil", "/konto/haslo", "/konto/awatar"):
            self.assertEqual(self.client.post(path).status_code, 400)
        self.assertEqual(self.user()["username"], "Alice")

    def test_password_validation_and_session_revocation(self):
        other = self.app.test_client()
        self.post(
            other, "/login", {"username": "Alice", "password": "old-password-123"}
        )
        valid = {
            "current_password": "old-password-123",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
        }
        for override in (
            {"current_password": "wrong"},
            {"new_password": "short", "confirm_password": "short"},
            {"confirm_password": "different"},
            {
                "new_password": "old-password-123",
                "confirm_password": "old-password-123",
            },
        ):
            response = self.post(self.client, "/konto/haslo", {**valid, **override})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(b'value="old-password-123"', response.data)
            self.assertTrue(
                check_password_hash(self.user()["password_hash"], "old-password-123")
            )
        self.assertEqual(
            self.post(self.client, "/konto/haslo", valid, follow=True).status_code, 200
        )
        self.assertTrue(
            check_password_hash(self.user()["password_hash"], "new-password-456")
        )
        self.assertEqual(other.get("/konto").location, "/login")
        self.assertEqual(
            self.post(other, "/konto/profil", {"username": "Stale"}).location, "/login"
        )
        self.post(self.client, "/logout")
        self.assertEqual(
            self.post(
                self.client,
                "/login",
                {"username": "Alice", "password": "old-password-123"},
            ).status_code,
            200,
        )
        self.assertEqual(
            self.post(
                self.client,
                "/login",
                {"username": "Alice", "password": "new-password-456"},
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get("/konto").status_code, 200)

    def test_avatar_formats_private_storage_and_removal(self):
        for format in ("PNG", "JPEG", "WEBP"):
            self.assertEqual(
                self.post(
                    self.client,
                    "/konto/awatar",
                    {"avatar": (self.image(format), "profile." + format.lower())},
                ).status_code,
                302,
            )
            response = self.client.get("/konto/awatar")
            self.assertEqual(response.mimetype, "image/png")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
            with Image.open(io.BytesIO(response.data)) as image:
                self.assertEqual(image.size, (256, 256))
                self.assertFalse(image.getexif())
        self.assertIn(b"/konto/awatar", self.client.get("/konto").data)
        other = self.app.test_client()
        self.register(other, "Bob")
        self.assertEqual(other.get("/konto/awatar").status_code, 404)
        self.assertEqual(self.app.test_client().get("/konto/awatar").location, "/login")
        self.post(self.client, "/konto/awatar", {"action": "remove"})
        self.assertEqual(self.client.get("/konto/awatar").status_code, 404)

    def test_invalid_images_do_not_replace_avatar(self):
        self.post(self.client, "/konto/awatar", {"avatar": (self.image(), "good.png")})
        original = self.client.get("/konto/awatar").data
        for data in (
            {},
            {"avatar": (io.BytesIO(b"<svg/>"), "image.png")},
            {"avatar": (io.BytesIO(b"x" * (2 * 1024 * 1024 + 1)), "big.png")},
            {"avatar": (io.BytesIO(self.image().getvalue()[:40]), "broken.png")},
        ):
            self.assertEqual(
                self.post(self.client, "/konto/awatar", data).status_code, 400
            )
            self.assertEqual(self.client.get("/konto/awatar").data, original)

    def test_demo_and_anonymous_access(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/konto").location, "/login")
        self.post(anonymous, "/demo")
        self.assertIn("konto demonstracyjne".encode(), anonymous.get("/konto").data)
        for path in ("/konto/profil", "/konto/haslo", "/konto/awatar"):
            self.assertEqual(self.post(anonymous, path).status_code, 403)

    def test_current_password_attempts_are_limited(self):
        data = {
            "current_password": "wrong",
            "new_password": "new-password-456",
            "confirm_password": "new-password-456",
        }
        for _ in range(10):
            self.assertEqual(
                self.post(self.client, "/konto/haslo", data).status_code, 400
            )
        self.assertEqual(self.post(self.client, "/konto/haslo", data).status_code, 429)
        self.assertTrue(
            check_password_hash(self.user()["password_hash"], "old-password-123")
        )

    def test_migration_from_existing_database(self):
        path = str(Path(self.directory.name) / "old.sqlite3")
        with sqlite3.connect(path) as db:
            for migration in sorted(Path("madra/migrations").glob("00[1-6]*.sql")):
                db.executescript(migration.read_text())
            db.execute("INSERT INTO users VALUES ('old','Existing','hash',0,'now')")
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE": path,
                "CLOUD_STATE_BUCKET": None,
            }
        )
        with app.app_context():
            self.assertEqual(get_db().execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertEqual(
                get_db().execute("SELECT username FROM users").fetchone()[0], "Existing"
            )
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = "old"
        self.assertEqual(client.get("/konto").status_code, 200)
