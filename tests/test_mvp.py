"""Behavioral integration tests. Every database and legacy file is synthetic."""

import json
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from werkzeug.security import generate_password_hash
from madra import create_app
from madra.db import get_db, transaction
from madra.services.learning import today_date, now_iso, choose_items
from madra.services.migration import import_legacy


class MVPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password_hash = generate_password_hash("strong-pass-123")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "test.sqlite3")
        self.app = create_app(
            {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": self.path}
        )
        self.client = self.app.test_client()
        self.uid, self.wid, self.tid = uuid4().hex, uuid4().hex, uuid4().hex
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO users VALUES (?,?,?,0,?)",
                (self.uid, "Alice", self.password_hash, now_iso()),
            )
            db.execute(
                "INSERT INTO workspaces VALUES (?,?,'Science','','blue',?,NULL)",
                (self.wid, self.uid, now_iso()),
            )
            db.execute(
                "INSERT INTO topics VALUES (?,?,'Energy','',?)",
                (self.tid, self.wid, now_iso()),
            )
        self.authenticate(self.client)

    def tearDown(self):
        self.directory.cleanup()

    def authenticate(self, client, uid=None):
        with client.session_transaction() as session:
            session["user_id"] = uid or self.uid
            session["csrf"] = "test-token"

    def post(self, path, data=None, client=None, follow=False):
        c = client or self.client
        with c.session_transaction() as session:
            token = session.get("csrf", "test-token")
            session["csrf"] = token
        return c.post(
            path, data={"csrf_token": token, **(data or {})}, follow_redirects=follow
        )

    def undo(self, sid):
        with self.app.app_context():
            review = (
                get_db()
                .execute(
                    "SELECT r.id FROM reviews r JOIN session_items i ON i.id=r.item_id WHERE i.session_id=? ORDER BY i.position DESC LIMIT 1",
                    (sid,),
                )
                .fetchone()[0]
            )
        return self.post(f"/nauka/{sid}/cofnij", {"review_id": review})

    def activity(
        self,
        kind="open",
        prompt="Explain energy",
        answer="A model answer",
        options=None,
        minutes=2,
    ):
        response = self.post(
            f"/tematy/{self.tid}/cwiczenia/nowe",
            {
                "kind": kind,
                "prompt": prompt,
                "answer": answer,
                "options": "\n".join(options or []),
                "minutes": minutes,
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            return (
                get_db()
                .execute("SELECT id FROM activities ORDER BY created_at DESC LIMIT 1")
                .fetchone()[0]
            )

    def start(self, budget=10):
        response = self.post("/nauka/start", {"budget": budget})
        self.assertEqual(response.status_code, 302)
        sid = response.location.rsplit("/", 1)[-1]
        with self.app.app_context():
            item = dict(
                get_db()
                .execute(
                    "SELECT * FROM session_items WHERE session_id=? ORDER BY position LIMIT 1",
                    (sid,),
                )
                .fetchone()
            )
        return sid, item

    def count(self, table):
        with self.app.app_context():
            return get_db().execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def reveal(self, sid, item, response="My explanation"):
        return self.post(
            f"/nauka/{sid}/odpowiedz", {"item_id": item["id"], "response": response}
        )

    def grade(self, sid, item, grade=2):
        return self.post(f"/nauka/{sid}/ocena", {"item_id": item["id"], "grade": grade})

    def test_full_learning_flow_and_persistence(self):
        self.post(
            f"/tematy/{self.tid}/materialy/nowy",
            {"kind": "note", "title": "Notes", "content": "My notes"},
        )
        self.activity("open")
        self.activity("exercise", "Write code", "print(42)")
        sid, item = self.start()
        self.assertEqual(self.client.get(f"/nauka/{sid}").status_code, 200)
        self.reveal(sid, item)
        self.grade(sid, item)
        with self.app.app_context():
            next_item = dict(
                get_db()
                .execute(
                    "SELECT * FROM session_items WHERE session_id=? AND position=1",
                    (sid,),
                )
                .fetchone()
            )
        self.reveal(sid, next_item, "print(42)")
        self.grade(sid, next_item)
        self.assertEqual(self.count("reviews"), 2)
        self.assertIn(
            "Przegląd odpowiedzi".encode(), self.client.get(f"/nauka/{sid}").data
        )
        other_app = create_app(
            {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": self.path}
        )
        with other_app.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 2
            )
        self.assertEqual(self.client.get("/postepy").status_code, 200)

    def test_csrf_blocks_mutation(self):
        self.assertEqual(
            self.client.post("/przedmioty/nowy", data={"name": "bad"}).status_code, 400
        )
        self.assertEqual(self.count("workspaces"), 1)

    def test_other_user_cannot_read_or_mutate(self):
        aid = self.activity()
        sid, item = self.start()
        uid = uuid4().hex
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO users VALUES (?,?,?,0,?)",
                (uid, "Bob", self.password_hash, now_iso()),
            )
        other = self.app.test_client()
        self.authenticate(other, uid)
        for path in (
            f"/przedmioty/{self.wid}",
            f"/tematy/{self.tid}",
            f"/cwiczenia/{aid}/edytuj",
            f"/nauka/{sid}",
        ):
            self.assertEqual(other.get(path).status_code, 404, path)
        self.assertEqual(
            self.post(f"/cwiczenia/{aid}/archiwizuj", client=other).status_code, 404
        )
        self.assertEqual(
            self.post(
                f"/nauka/{sid}/ocena", {"item_id": item["id"], "grade": 2}, client=other
            ).status_code,
            404,
        )
        exported = json.loads(other.get("/konto/eksport").data)
        self.assertEqual(exported["workspaces"], [])

    def test_no_grading_before_answer(self):
        self.activity()
        sid, item = self.start()
        self.assertEqual(self.grade(sid, item).status_code, 409)
        self.assertEqual(self.count("reviews"), 0)

    def test_double_submission_is_idempotent(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item)
        self.grade(sid, item)
        self.assertEqual(self.count("reviews"), 1)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT reviews FROM progress").fetchone()[0], 1
            )

    def test_concurrent_submission_is_idempotent(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)

        def submit(_):
            client = self.app.test_client()
            self.authenticate(client)
            return self.post(
                f"/nauka/{sid}/ocena",
                {"item_id": item["id"], "grade": 2},
                client=client,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(submit, range(2))), [302, 302])
        self.assertEqual(self.count("reviews"), 1)

    def test_quiz_correctness_is_server_side(self):
        self.activity("quiz", "Choose", "Right", ["Right", "Wrong"])
        sid, item = self.start()
        self.reveal(sid, item, "Wrong")
        self.grade(sid, item, 3)
        with self.app.app_context():
            row = (
                get_db()
                .execute("SELECT grade,objective_correct FROM reviews")
                .fetchone()
            )
            self.assertEqual(tuple(row), (0, 0))
        self.undo(sid)
        # The frozen attempted answer cannot be changed after revealing.
        self.reveal(sid, item, "Right")
        self.grade(sid, item, 3)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT grade FROM reviews").fetchone()[0], 0
            )

    def test_quiz_correct_answer(self):
        self.activity("quiz", "Choose", "Right", ["Right", "Wrong"])
        sid, item = self.start()
        self.reveal(sid, item, "Right")
        self.grade(sid, item, 0)
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT grade FROM reviews").fetchone()[0], 2
            )

    def test_quiz_does_not_render_answer_before_attempt(self):
        self.activity("quiz", "Choose", "Right", ["Right", "Wrong"])
        sid, item = self.start()
        text = self.client.get(f"/nauka/{sid}").get_data(as_text=True)
        self.assertNotIn("Poprawna odpowiedź!", text)
        self.assertNotIn("objective_correct", text)
        self.assertNotIn("snapshot_json", text)

    def test_edit_keeps_id_history_and_session_snapshot(self):
        aid = self.activity(prompt="Original prompt")
        sid, item = self.start()
        self.post(
            f"/cwiczenia/{aid}/edytuj",
            {
                "kind": "open",
                "prompt": "Changed prompt",
                "answer": "New answer",
                "minutes": 3,
            },
        )
        text = self.client.get(f"/nauka/{sid}").get_data(as_text=True)
        self.assertIn("Original prompt", text)
        self.assertNotIn("Changed prompt", text)
        self.reveal(sid, item)
        self.grade(sid, item)
        self.assertEqual(self.count("activities"), 1)
        self.assertEqual(self.count("progress"), 1)

    def test_active_session_resumes_without_duplication(self):
        self.activity()
        sid, _ = self.start()
        response = self.post("/nauka/start", {"budget": 5})
        self.assertTrue(response.location.endswith(sid))
        self.assertEqual(self.count("study_sessions"), 1)

    def test_undo_restores_previous_state(self):
        aid = self.activity()
        with self.app.app_context(), transaction() as db:
            original = (
                self.uid,
                aid,
                5,
                4,
                2,
                30,
                (today_date() - timedelta(days=1)).isoformat(),
                now_iso(),
            )
            db.execute("INSERT INTO progress VALUES (?,?,?,?,?,?,?,?)", original)
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        self.assertEqual(self.undo(sid).status_code, 302)
        with self.app.app_context():
            self.assertEqual(
                tuple(get_db().execute("SELECT * FROM progress").fetchone()), original
            )
        self.assertEqual(self.count("reviews"), 0)

    def test_failure_reschedules_to_tomorrow(self):
        aid = self.activity()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO progress VALUES (?,?,5,5,3,30,?,?)",
                (self.uid, aid, "2099-01-01", now_iso()),
            )
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        with self.app.app_context():
            row = (
                get_db()
                .execute("SELECT due_date,interval_days FROM progress")
                .fetchone()
            )
            self.assertEqual(
                tuple(row), ((today_date() + timedelta(days=1)).isoformat(), 1)
            )

    def test_storage_failure_rolls_back(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        with (
            self.assertLogs(self.app.logger, level="ERROR"),
            patch(
                "madra.study.save_progress",
                side_effect=sqlite3.OperationalError("synthetic failure"),
            ),
        ):
            self.assertEqual(self.grade(sid, item).status_code, 503)
        self.assertEqual(self.count("reviews"), 0)
        self.assertEqual(self.count("progress"), 0)

    def test_unsafe_links_rejected_and_notes_escaped(self):
        response = self.post(
            f"/tematy/{self.tid}/materialy/nowy",
            {"kind": "link", "title": "Unsafe", "content": "javascript:alert(1)"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.count("materials"), 0)
        self.post(
            f"/tematy/{self.tid}/materialy/nowy",
            {"kind": "note", "title": "Safe", "content": "<script>alert(1)</script>"},
        )
        text = self.client.get(f"/tematy/{self.tid}").get_data(as_text=True)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>alert(1)</script>", text)

    def test_invalid_activity_and_goal_are_not_saved(self):
        self.post(
            f"/tematy/{self.tid}/cwiczenia/nowe",
            {
                "kind": "quiz",
                "prompt": "Bad",
                "answer": "missing",
                "options": "A\nA",
                "minutes": 2,
            },
        )
        self.assertEqual(self.count("activities"), 0)
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Bad",
                "target_date": "2020-01-01",
                "daily_minutes": 0,
            },
        )
        self.assertEqual(self.count("goals"), 0)

    def test_goal_export_and_archiving(self):
        aid = self.activity()
        with self.app.app_context():
            target = (today_date() + timedelta(days=20)).isoformat()
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Exam",
                "target_date": target,
                "daily_minutes": 20,
            },
        )
        self.assertEqual(self.count("goals"), 1)
        exported = json.loads(self.client.get("/konto/eksport").data)
        self.assertEqual(len(exported["activities"]), 1)
        self.assertNotIn("password_hash", json.dumps(exported))
        self.post(f"/cwiczenia/{aid}/archiwizuj")
        self.assertEqual(self.count("activities"), 1)
        self.assertEqual(
            self.post("/nauka/start", {"budget": 10}).location, "/biblioteka"
        )

    def test_legacy_import_dry_run_idempotent_preserves_raw_history(self):
        path = Path(self.directory.name) / "legacy.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "old",
                        "autor": "Alice",
                        "nazwa": "Old set",
                        "historia_nauki": [{"data": "2020-01-01"}],
                        "karty": [
                            {
                                "tekst": "Q",
                                "odpowiedz": "A",
                                "statystyki": {"pokazane": 9},
                            }
                        ],
                    }
                ]
            )
        )
        with self.app.app_context():
            result = import_legacy(str(path))
            self.assertEqual(result["activities"], 1)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM activities").fetchone()[0], 0
            )
            import_legacy(str(path), apply=True)
            self.assertEqual(import_legacy(str(path), apply=True)["workspaces"], 0)
            payload = json.loads(
                get_db()
                .execute("SELECT payload_json FROM legacy_payloads")
                .fetchone()[0]
            )
            self.assertEqual(payload["historia_nauki"][0]["data"], "2020-01-01")
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0
            )

    def test_legacy_import_unknown_owner_does_not_write(self):
        path = Path(self.directory.name) / "legacy.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "id": "old",
                        "autor": "Unknown",
                        "karty": [{"tekst": "Q", "odpowiedz": "A"}],
                    }
                ]
            )
        )
        with self.app.app_context():
            with self.assertRaises(ValueError):
                import_legacy(str(path), apply=True)
        self.assertEqual(self.count("workspaces"), 1)

    def test_demo_isolated_and_all_pages_work(self):
        guest = self.app.test_client()
        guest.get("/")
        self.post("/demo", client=guest, follow=True)
        for route in ("/dzisiaj", "/biblioteka", "/cele", "/postepy"):
            self.assertEqual(guest.get(route).status_code, 200)
        export = json.loads(guest.get("/konto/eksport").data)
        self.assertEqual(len(export["workspaces"]), 3)
        self.assertFalse(any(x["id"] == self.wid for x in export["workspaces"]))

    def test_registration_login_and_logout(self):
        guest = self.app.test_client()
        response = self.post(
            "/register",
            {
                "username": "New learner",
                "email": "new@example.test",
                "password": "new-pass-123",
                "confirm_password": "new-pass-123",
            },
            client=guest,
        )
        self.assertEqual(response.status_code, 302)
        self.post("/logout", client=guest)
        self.assertEqual(guest.get("/dzisiaj").status_code, 302)
        self.assertEqual(
            self.post(
                "/login",
                {"username": "New learner", "password": "new-pass-123"},
                client=guest,
            ).status_code,
            302,
        )
        self.assertEqual(guest.get("/dzisiaj").status_code, 200)

    def test_queue_prioritizes_due_and_respects_budget(self):
        items = [
            {"state": "due", "minutes": 3},
            {"state": "new", "minutes": 2},
            {"state": "scheduled", "minutes": 1},
        ]
        self.assertEqual(choose_items(items, 5), items[:2])

    def test_get_pages_do_not_save_reviews(self):
        self.activity()
        sid, _ = self.start()
        for _ in range(2):
            self.client.get(f"/nauka/{sid}")
            self.client.get("/dzisiaj")
        self.assertEqual(self.count("reviews"), 0)

    def test_encrypted_legacy_user_can_log_in_after_import(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        users_path = Path(self.directory.name) / "encrypted-users.json"
        sets_path = Path(self.directory.name) / "encrypted-sets.json"
        users_path.write_bytes(
            Fernet(key).encrypt(
                json.dumps(
                    {"users": [{"login": "Old learner", "haslo": self.password_hash}]}
                ).encode()
            )
        )
        sets_path.write_text(
            json.dumps(
                [
                    {
                        "id": "source-1",
                        "autor": "Old learner",
                        "nazwa": "Imported",
                        "karty": [{"tekst": "Q", "odpowiedz": "A"}],
                    }
                ]
            )
        )
        with patch.dict(os.environ, {"LEGACY_ENCRYPTION_KEY": key.decode()}):
            runner = self.app.test_cli_runner()
            result = runner.invoke(
                args=[
                    "import-legacy",
                    "--sets",
                    str(sets_path),
                    "--users",
                    str(users_path),
                    "--apply",
                ]
            )
        self.assertEqual(result.exit_code, 0, result.output)
        guest = self.app.test_client()
        self.assertEqual(
            self.post(
                "/login",
                {"username": "Old learner", "password": "strong-pass-123"},
                client=guest,
            ).status_code,
            302,
        )
        exported = json.loads(guest.get("/konto/eksport").data)
        self.assertEqual(len(exported["activities"]), 1)
        self.assertEqual(len(exported["reviews"]), 0)

    def test_failed_login_is_rate_limited(self):
        guest = self.app.test_client()
        for _ in range(10):
            self.assertEqual(
                self.post(
                    "/login", {"username": "missing", "password": "wrong"}, client=guest
                ).status_code,
                200,
            )
        self.assertEqual(
            self.post(
                "/login", {"username": "missing", "password": "wrong"}, client=guest
            ).status_code,
            429,
        )

    def test_user_day_uses_warsaw_timezone(self):
        class FixedClock(datetime):
            @classmethod
            def now(cls, tz=None):
                fixed = datetime(2026, 10, 11, 23, 30, tzinfo=timezone.utc)
                return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)

        with (
            self.app.app_context(),
            patch("madra.services.learning.datetime", FixedClock),
        ):
            self.assertEqual(today_date().isoformat(), "2026-10-12")

    def test_production_requires_secret_and_disables_demo(self):
        with patch.dict(os.environ, {"MADRA_ENV": "production"}):
            with self.assertRaises(RuntimeError):
                create_app({"SECRET_KEY": None, "DATABASE": self.path})
            production = create_app({"SECRET_KEY": "configured", "DATABASE": self.path})
            self.assertTrue(production.config["SESSION_COOKIE_SECURE"])
            self.assertFalse(production.config["ALLOW_DEMO"])

    def test_activity_form_has_usable_numeric_default(self):
        class InputParser(HTMLParser):
            inputs = None

            def handle_starttag(self, tag, attrs):
                if tag == "input":
                    self.inputs.append(dict(attrs))

        parser = InputParser()
        parser.inputs = []
        parser.feed(
            self.client.get(f"/tematy/{self.tid}/cwiczenia/nowe").get_data(as_text=True)
        )
        value = next(
            item["value"] for item in parser.inputs if item.get("name") == "minutes"
        )
        self.assertEqual(value, "2")


if __name__ == "__main__":
    unittest.main()
