"""Release regressions use synthetic users, files and storage only."""

import io
import json
import os
import sqlite3
import unittest
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from flask import g
from werkzeug.exceptions import Conflict
from madra.db import get_db, transaction
from madra.auth import USER_QUERY
from madra.services.learning import now_iso, today_date
import test_mvp as mvp_fixtures
import test_cloud as cloud_fixtures


class ReleaseTests(unittest.TestCase):
    setUpClass = classmethod(mvp_fixtures.MVPTests.setUpClass.__func__)
    setUp = mvp_fixtures.MVPTests.setUp
    tearDown = mvp_fixtures.MVPTests.tearDown
    authenticate = mvp_fixtures.MVPTests.authenticate
    post = mvp_fixtures.MVPTests.post
    activity = mvp_fixtures.MVPTests.activity
    start = mvp_fixtures.MVPTests.start
    reveal = mvp_fixtures.MVPTests.reveal
    grade = mvp_fixtures.MVPTests.grade

    def register(self, client, address="new@example.test", name="New Student"):
        return self.post(
            "/register",
            {
                "username": name,
                "email": address,
                "password": "new-password-123",
                "confirm_password": "new-password-123",
            },
            client=client,
        )

    def test_email_registration_login_and_legacy_login(self):
        guest = self.app.test_client()
        self.assertEqual(self.register(guest, " New@Example.Test ").status_code, 302)
        with guest.session_transaction() as session:
            self.assertIn("user_id", session)
        self.assertIn(b"new@example.test", guest.get("/konto").data)
        self.post("/logout", client=guest)
        self.post(
            "/login",
            {"username": "NEW@example.test", "password": "new-password-123"},
            client=guest,
        )
        self.assertEqual(guest.get("/konto").status_code, 200)
        self.assertEqual(self.client.get("/konto").status_code, 200)

    def test_email_validation_and_unique_address(self):
        for address in (
            "",
            "missing-at",
            "a@localhost",
            "a..b@example.test",
            "a@-bad.test",
            "a@example.test\nBcc:x@y.test",
        ):
            with self.subTest(address=address):
                self.assertEqual(
                    self.register(self.app.test_client(), address).status_code, 400
                )
        self.register(self.app.test_client())
        response = self.register(
            self.app.test_client(), "NEW@example.test", "Another Student"
        )
        self.assertIn("już zajęty".encode(), response.data)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM user_emails").fetchone()[0], 1
            )

    def test_archive_restore_preserves_history_and_isolation(self):
        aid = self.activity()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO progress VALUES (?,?,4,3,2,5,?,?)",
                (self.uid, aid, today_date().isoformat(), now_iso()),
            )
        self.post(f"/cwiczenia/{aid}/archiwizuj")
        response = self.client.get(f"/tematy/{self.tid}")
        self.assertIn("Archiwum ćwiczeń (1)".encode(), response.data)
        other = self.app.test_client()
        self.register(other)
        self.assertEqual(
            self.post(f"/cwiczenia/{aid}/przywroc", client=other).status_code, 404
        )
        self.assertEqual(
            self.client.post(f"/cwiczenia/{aid}/przywroc").status_code, 400
        )
        self.post(f"/cwiczenia/{aid}/przywroc")
        self.post(f"/cwiczenia/{aid}/przywroc")
        with self.app.app_context():
            self.assertEqual(
                get_db()
                .execute("SELECT reviews FROM progress WHERE activity_id=?", (aid,))
                .fetchone()[0],
                4,
            )
            self.assertEqual(
                get_db()
                .execute("SELECT archived FROM activities WHERE id=?", (aid,))
                .fetchone()[0],
                0,
            )

    def test_search_content_casefold_escaping_and_isolation(self):
        self.activity(prompt="ŻÓŁĆ <script>needle</script>")
        self.post(
            f"/tematy/{self.tid}/materialy/nowy",
            {"title": "A note", "kind": "note", "content": "Some needle content"},
        )
        response = self.client.get("/biblioteka?q=needle")
        self.assertIn(b"A note", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b"<script>needle", response.data)
        response = self.client.get("/biblioteka?q=żółć")
        self.assertIn("ŻÓŁĆ".encode(), response.data)
        other = self.app.test_client()
        self.register(other)
        self.assertNotIn(b"A note", other.get("/biblioteka?q=needle").data)

    def test_goal_edit_week_delete_preserves_learning(self):
        self.activity(minutes=3)
        with self.app.app_context():
            target = (today_date() + timedelta(days=4)).isoformat()
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Exam",
                "target_date": target,
                "daily_minutes": 20,
            },
        )
        with self.app.app_context():
            gid = get_db().execute("SELECT id FROM goals").fetchone()[0]
        response = self.client.get("/cele")
        self.assertIn("Najbliższy tydzień".encode(), response.data)
        self.assertEqual(
            self.post(
                f"/cele/{gid}/edytuj",
                {"title": "New exam", "target_date": target, "daily_minutes": 30},
            ).status_code,
            302,
        )
        self.assertEqual(
            self.post(
                f"/cele/{gid}/edytuj",
                {"title": "bad", "target_date": "garbage", "daily_minutes": 999},
            ).status_code,
            400,
        )
        other = self.app.test_client()
        self.register(other)
        self.assertEqual(self.post(f"/cele/{gid}/usun", client=other).status_code, 404)
        self.assertEqual(self.client.post(f"/cele/{gid}/usun").status_code, 400)
        self.post(f"/cele/{gid}/usun")
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM goals").fetchone()[0], 0
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM activities").fetchone()[0], 1
            )

    def test_archive_contains_originals_without_credentials(self):
        self.post(
            "/materialy/wgraj",
            {"file": (io.BytesIO(b"Synthetic note"), "note.txt"), "topic_id": self.tid},
        )
        response = self.client.get("/konto/archiwum")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            data = json.loads(archive.read("data.json"))
            self.assertEqual(data["username"], "Alice")
            self.assertEqual(
                archive.read(data["originals"][0]["path"]), b"Synthetic note"
            )
            self.assertNotIn("password_hash", json.dumps(data))
        response.close()
        other = self.app.test_client()
        self.register(other)
        response = other.get("/konto/archiwum")
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(json.loads(archive.read("data.json"))["originals"], [])
        response.close()

    def test_delete_account_confirmation_and_complete_cleanup(self):
        self.activity()
        self.post(
            "/materialy/wgraj",
            {"file": (io.BytesIO(b"Synthetic note"), "note.txt"), "topic_id": self.tid},
        )
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 2)
        with self.app.app_context():
            target = (today_date() + timedelta(days=3)).isoformat()
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Exam",
                "target_date": target,
                "daily_minutes": 20,
            },
        )
        other = self.app.test_client()
        self.register(other)
        self.assertEqual(self.client.post("/konto/usun").status_code, 400)
        self.assertEqual(
            self.post(
                "/konto/usun",
                {"current_password": "wrong", "confirm_username": "Alice"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/konto/usun",
                {"current_password": "strong-pass-123", "confirm_username": "wrong"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "/konto/usun",
                {"current_password": "strong-pass-123", "confirm_username": "Alice"},
            ).status_code,
            302,
        )
        self.assertEqual(self.client.get("/konto").location, "/login")
        self.assertEqual(other.get("/konto").status_code, 200)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(
                db.execute(
                    "SELECT COUNT(*) FROM users WHERE id=?", (self.uid,)
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM uploads").fetchone()[0], 0
            )
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM activities").fetchone()[0], 0
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_delete_blocks_connected_chatgpt_and_running_jobs(self):
        from madra.services import chatgpt

        with self.app.app_context():
            chatgpt.save(self.uid, {"tokens": {"access_token": "synthetic"}})
        data = {"current_password": "strong-pass-123", "confirm_username": "Alice"}
        self.assertEqual(self.post("/konto/usun", data).status_code, 409)
        with self.app.app_context():
            chatgpt.save(self.uid, {})
        self.post(
            "/materialy/wgraj",
            {"file": (io.BytesIO(b"Synthetic note"), "note.txt"), "topic_id": self.tid},
        )
        with self.app.app_context(), transaction() as db:
            upload = db.execute("SELECT id FROM uploads").fetchone()[0]
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,created_at) VALUES ('job',?,?,'running','synthetic','test',?)",
                (upload, self.uid, now_iso()),
            )
        self.assertEqual(self.post("/konto/usun", data).status_code, 409)
        self.assertEqual(self.client.get("/konto").status_code, 200)

    def test_ip_limit_cannot_be_bypassed_by_changing_usernames(self):
        guest = self.app.test_client()
        for i in range(60):
            self.assertEqual(
                self.post(
                    "/login", {"username": f"unknown-{i}", "password": ""}, client=guest
                ).status_code,
                200,
            )
        self.assertEqual(
            self.post(
                "/login", {"username": "another-name", "password": ""}, client=guest
            ).status_code,
            429,
        )

    def test_stale_authenticated_write_is_rejected(self):
        with self.app.test_request_context():
            g.user = (
                get_db()
                .execute(USER_QUERY + " WHERE users.id=?", (self.uid,))
                .fetchone()
            )
            with sqlite3.connect(self.path) as external:
                external.execute(
                    "INSERT INTO user_profiles (user_id,session_version) VALUES (?,1)",
                    (self.uid,),
                )
            with self.assertRaises(Conflict), transaction() as db:
                db.execute("UPDATE users SET username='Stale' WHERE id=?", (self.uid,))
            self.assertEqual(
                get_db()
                .execute("SELECT username FROM users WHERE id=?", (self.uid,))
                .fetchone()[0],
                "Alice",
            )

    def test_concurrent_login_limit_is_atomic(self):
        def attempt(_):
            client = self.app.test_client()
            return self.post(
                "/login", {"username": "missing", "password": "wrong"}, client=client
            ).status_code

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(attempt, range(12)))
        self.assertEqual(statuses.count(429), 2)

    def test_undo_same_timestamp_and_retry_do_not_remove_prior_review(self):
        self.activity(prompt="First question")
        self.activity(prompt="Second question")
        sid, first = self.start()
        self.reveal(sid, first)
        with patch("madra.study.now_iso", return_value="2026-10-13T10:00:00+00:00"):
            self.grade(sid, first, 2)
            with self.app.app_context():
                second = (
                    get_db()
                    .execute(
                        "SELECT * FROM session_items WHERE session_id=? ORDER BY position DESC LIMIT 1",
                        (sid,),
                    )
                    .fetchone()
                )
            self.reveal(sid, second)
            self.grade(sid, second, 2)
        with self.app.app_context():
            review = (
                get_db()
                .execute("SELECT id FROM reviews WHERE item_id=?", (second["id"],))
                .fetchone()[0]
            )
        self.assertEqual(self.client.post(f"/nauka/{sid}/cofnij").status_code, 400)
        self.assertEqual(
            self.post(f"/nauka/{sid}/cofnij", {"review_id": review}).status_code, 302
        )
        self.assertEqual(
            self.post(f"/nauka/{sid}/cofnij", {"review_id": review}).status_code, 302
        )
        with self.app.app_context():
            rows = get_db().execute("SELECT item_id FROM reviews").fetchall()
            self.assertEqual([row[0] for row in rows], [first["id"]])

    def test_database_backup_can_be_reopened_and_is_exclusive(self):
        self.activity()
        path = Path(self.directory.name) / "backup.sqlite3"
        runner = self.app.test_cli_runner()
        result = runner.invoke(args=["backup-db", str(path)])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        self.assertEqual(runner.invoke(args=["verify-backup", str(path)]).exit_code, 0)
        self.assertNotEqual(runner.invoke(args=["backup-db", str(path)]).exit_code, 0)
        with sqlite3.connect(path) as restored:
            self.assertEqual(
                restored.execute("SELECT COUNT(*) FROM activities").fetchone()[0], 1
            )
            self.assertEqual(restored.execute("PRAGMA user_version").fetchone()[0], 9)


class CloudReleaseTests(unittest.TestCase):
    setUp = cloud_fixtures.CloudTests.setUp
    tearDown = cloud_fixtures.CloudTests.tearDown
    make_app = cloud_fixtures.CloudTests.make_app
    post = cloud_fixtures.CloudTests.post

    def test_email_is_durable_after_restart(self):
        restarted = self.make_app().test_client()
        with restarted.session_transaction() as session:
            session["csrf"] = "csrf"
        restarted.post(
            "/login",
            data={
                "csrf_token": "csrf",
                "username": "cloud@example.test",
                "password": "test-password-123",
            },
        )
        self.assertEqual(restarted.get("/konto").status_code, 200)

    def test_readonly_exports_do_not_republish_cloud_state(self):
        version = self.cloud.objects["madra-v2/state.sqlite3"][1]
        self.assertEqual(self.client.get("/konto/eksport").status_code, 200)
        response = self.client.get("/konto/archiwum")
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertEqual(self.cloud.objects["madra-v2/state.sqlite3"][1], version)

    def test_delete_is_durable_and_clears_identity_metadata(self):
        with self.app.app_context():
            cloud_fixtures.chatgpt.save(
                self.uid, {"email": "private@example.test", "client_id": "synthetic"}
            )
        self.assertEqual(
            self.post(
                "/konto/usun",
                {
                    "current_password": "test-password-123",
                    "confirm_username": "CloudStudent",
                },
            ).status_code,
            302,
        )
        restarted = self.make_app()
        with restarted.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0], 0
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM user_emails").fetchone()[0], 0
            )
            self.assertEqual(cloud_fixtures.chatgpt.load(self.uid), {})

    def test_failed_cloud_delete_preserves_account(self):
        self.cloud.fail_write = True
        response = self.post(
            "/konto/usun",
            {
                "current_password": "test-password-123",
                "confirm_username": "CloudStudent",
            },
        )
        self.assertEqual(response.status_code, 503)
        self.cloud.fail_write = False
        self.assertEqual(self.client.get("/konto").status_code, 200)
