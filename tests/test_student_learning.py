"""Student journeys: understanding, mistakes, scope, exams, imports and formatting."""

import io
import json
import sqlite3
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import timedelta
from madra import create_app
from madra.db import get_db, transaction
from madra.planning import goal_details
from madra.services.learning import today_date, now_iso
from madra.services.formatting import render_content
import test_mvp as fixtures
import test_cloud as cloud_fixtures


class StudentTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.MVPTests.setUpClass.__func__)
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    authenticate = fixtures.MVPTests.authenticate
    post = fixtures.MVPTests.post
    activity = fixtures.MVPTests.activity
    start = fixtures.MVPTests.start
    reveal = fixtures.MVPTests.reveal
    grade = fixtures.MVPTests.grade

    def rows(self, sql, args=()):
        with self.app.app_context():
            return [dict(r) for r in get_db().execute(sql, args)]

    def latest_item(self, sid, position=0):
        return self.rows(
            "SELECT * FROM session_items WHERE session_id=? ORDER BY position", (sid,)
        )[position]

    def other(self):
        client = self.app.test_client()
        self.post(
            "/register",
            {
                "username": "Other student",
                "email": "other@example.test",
                "password": "other-password-123",
                "confirm_password": "other-password-123",
            },
            client=client,
        )
        return client

    def goal(self, topics=None, weekdays=None):
        with self.app.app_context():
            target = (today_date() + timedelta(days=7)).isoformat()
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Exam",
                "target_date": target,
                "daily_minutes": 30,
            },
        )
        gid = self.rows("SELECT id FROM goals")[0]["id"]
        if topics is not None:
            self.post(
                "/cele/" + gid + "/edytuj",
                {
                    "title": "Exam",
                    "target_date": target,
                    "daily_minutes": 30,
                    "schedule_configured": "1",
                    "topic_ids": topics,
                    "weekdays": (
                        weekdays if weekdays is not None else [str(i) for i in range(7)]
                    ),
                    "priority_" + self.tid: "3",
                },
            )
        return gid

    def topic(self, name="Second topic"):
        return self.post(
            f"/przedmioty/{self.wid}/tematy/nowy", {"name": name}
        ).location.rsplit("/", 1)[-1]

    def test_summary_preserves_question_response_and_frozen_explanation(self):
        aid = self.activity()
        self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "open",
                "prompt": "Original question",
                "answer": "Original answer",
                "minutes": 2,
                "hints": ["Step one", "Step two"],
                "explanation": "Original reasoning",
                "rubric": "A complete answer explains the mechanism.",
            },
        )
        sid, item = self.start()
        self.reveal(sid, item, "My own answer")
        self.post(
            f"/nauka/{sid}/ocena",
            {
                "item_id": item["id"],
                "grade": 0,
                "used_help": "1",
                "error_reason": "reasoning",
            },
        )
        self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "open",
                "prompt": "Changed question",
                "answer": "Changed answer",
                "minutes": 2,
                "explanation": "Changed reasoning",
            },
        )
        html = self.client.get("/nauka/" + sid).get_data(as_text=True)
        for text in (
            "Original question",
            "Original answer",
            "Original reasoning",
            "My own answer",
            "Z pomocą",
            "tok rozumowania",
        ):
            self.assertIn(text, html)
        self.assertNotIn("Changed reasoning", html)

    def test_difficult_mode_includes_scheduled_errors_and_preserves_history(self):
        aid = self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        response = self.post(
            "/nauka/start", {"topic_id": self.tid, "mode": "difficult", "budget": 5}
        )
        self.assertEqual(response.status_code, 302)
        second = response.location.rsplit("/", 1)[-1]
        item2 = self.latest_item(second)
        self.assertEqual(item2["activity_id"], aid)
        self.reveal(second, item2)
        self.grade(second, item2, 2)
        self.assertEqual(len(self.rows("SELECT * FROM reviews")), 2)
        self.assertEqual(self.rows("SELECT reviews FROM progress")[0]["reviews"], 2)
        self.assertEqual(
            self.post(
                "/nauka/start", {"topic_id": self.tid, "mode": "difficult", "budget": 5}
            ).location,
            "/tematy/" + self.tid,
        )

    def test_error_keeps_nonzero_plan_and_reports_unchecked_topics(self):
        self.activity("quiz", answer="Right", options=["Wrong", "Right"])
        for i in range(7):
            self.topic("Topic " + str(i))
        self.goal()
        sid, item = self.start()
        self.reveal(sid, item, "Wrong")
        self.grade(sid, item)
        with self.app.app_context():
            goal = goal_details(self.uid)[0]
            self.assertEqual(goal["unchecked_topics"], 7)
            self.assertEqual(goal["weak"], 1)
            self.assertGreater(goal["estimated_remaining"], 0)
            self.assertGreater(sum(day["minutes"] for day in goal["week"]), 0)
        html = self.client.get("/cele").get_data(as_text=True)
        self.assertIn("Zakres niesprawdzony", html)

    def test_goal_scope_and_weekdays_control_plan(self):
        included = self.activity()
        tid2 = self.topic()
        self.post(
            f"/tematy/{tid2}/cwiczenia/nowe",
            {
                "kind": "open",
                "prompt": "Excluded question",
                "answer": "Excluded answer",
                "minutes": 2,
            },
        )
        with self.app.app_context():
            day = str((today_date().weekday() + 1) % 7)
        gid = self.goal([self.tid], [day])
        with self.app.app_context():
            goal = goal_details(self.uid)[0]
            self.assertEqual(goal["total"], 1)
            self.assertFalse(goal["week"][0]["available"])
            self.assertTrue(any(d["minutes"] > 0 for d in goal["week"]))
        response = self.post("/nauka/start", {"goal_id": gid, "budget": 5})
        sid = response.location.rsplit("/", 1)[-1]
        self.assertEqual(
            [
                r["activity_id"]
                for r in self.rows(
                    "SELECT * FROM session_items WHERE session_id=?", (sid,)
                )
            ],
            [included],
        )
        self.assertEqual(
            self.client.get("/nauka/przygotuj?goal_id=" + gid).status_code, 200
        )

    def test_topic_importance_changes_session_order(self):
        self.activity(prompt="Low priority")
        tid = self.topic("Important topic")
        self.post(
            f"/tematy/{tid}/cwiczenia/nowe",
            {
                "kind": "open",
                "prompt": "High priority",
                "answer": "Answer",
                "minutes": 2,
            },
        )
        gid = self.goal([self.tid, tid])
        with self.app.app_context():
            target = (today_date() + timedelta(days=7)).isoformat()
        self.post(
            f"/cele/{gid}/edytuj",
            {
                "title": "Exam",
                "target_date": target,
                "daily_minutes": 30,
                "schedule_configured": "1",
                "topic_ids": [self.tid, tid],
                "weekdays": ["0", "1", "2", "3", "4", "5", "6"],
                "priority_" + self.tid: 1,
                "priority_" + tid: 3,
            },
        )
        sid = self.post("/nauka/start", {"goal_id": gid, "budget": 5}).location.rsplit(
            "/", 1
        )[-1]
        self.assertEqual(
            json.loads(self.latest_item(sid)["snapshot_json"])["prompt"],
            "High priority",
        )

    def test_history_pagination_keeps_old_sessions_reachable(self):
        with self.app.app_context(), transaction() as db:
            for i in range(11):
                db.execute(
                    "INSERT INTO study_sessions VALUES (?,?,?,5,'completed',?,?)",
                    (
                        f"session-{i}",
                        self.uid,
                        f"Historical {i}",
                        f"2026-10-{i+1:02d}T10:00:00+00:00",
                        now_iso(),
                    ),
                )
        first = self.client.get("/postepy").get_data(as_text=True)
        second = self.client.get("/postepy?page=2").get_data(as_text=True)
        self.assertIn("Starsze sesje", first)
        self.assertNotIn("Historical 0", first)
        self.assertIn("Historical 0", second)
        self.assertEqual(self.client.get("/postepy?page=0").status_code, 400)

    def test_goal_rejects_foreign_scope_and_empty_days_atomically(self):
        gid = self.goal()
        other = self.other()
        wid = self.post(
            "/przedmioty/nowy", {"name": "Private", "color": "blue"}, client=other
        ).location.rsplit("/", 1)[-1]
        tid = self.post(
            "/przedmioty/" + wid + "/tematy/nowy", {"name": "Private"}, client=other
        ).location.rsplit("/", 1)[-1]
        with self.app.app_context():
            target = (today_date() + timedelta(days=8)).isoformat()
        data = {
            "title": "Bad change",
            "target_date": target,
            "daily_minutes": 30,
            "schedule_configured": "1",
            "topic_ids": [tid],
            "weekdays": ["1"],
        }
        self.assertEqual(self.post("/cele/" + gid + "/edytuj", data).status_code, 400)
        data["topic_ids"] = [self.tid]
        data["weekdays"] = []
        self.assertEqual(self.post("/cele/" + gid + "/edytuj", data).status_code, 400)
        self.assertEqual(self.rows("SELECT title FROM goals")[0]["title"], "Exam")

    def test_switch_pauses_session_and_resume_preserves_answer(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item, "Preserved answer")
        tid = self.topic()
        self.post(
            "/tematy/" + tid + "/cwiczenia/nowe",
            {
                "kind": "flashcard",
                "prompt": "Other question",
                "answer": "Other answer",
                "minutes": 2,
            },
        )
        conflict = self.post("/nauka/start", {"topic_id": tid, "budget": 5})
        self.assertEqual(conflict.status_code, 409)
        self.assertIn("Zapisz przerwę", conflict.get_data(as_text=True))
        response = self.post(
            "/nauka/start",
            {"topic_id": tid, "budget": 5, "switch": "1", "active_id": sid},
        )
        second = response.location.rsplit("/", 1)[-1]
        self.assertNotEqual(sid, second)
        self.assertEqual(
            self.rows("SELECT paused FROM session_settings WHERE session_id=?", (sid,))[
                0
            ]["paused"],
            1,
        )
        self.assertEqual(self.post("/nauka/" + sid + "/wznow").status_code, 409)
        self.assertEqual(
            self.post(
                "/nauka/" + sid + "/wznow", {"switch": "1", "active_id": second}
            ).status_code,
            302,
        )
        self.assertIn(
            "Preserved answer", self.client.get("/nauka/" + sid).get_data(as_text=True)
        )

    def make_exam(self):
        self.activity(
            "quiz", prompt="Quiz question", answer="Right", options=["Wrong", "Right"]
        )
        aid = self.activity(
            "open", prompt="Explain independently", answer="SECRET_MODEL_ANSWER"
        )
        self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "open",
                "prompt": "Explain independently",
                "answer": "SECRET_MODEL_ANSWER",
                "minutes": 2,
                "hints": ["SECRET_HINT"],
                "explanation": "SECRET_REASON",
                "rubric": "SECRET_CRITERIA",
            },
        )
        response = self.post(
            "/nauka/start", {"mode": "exam", "budget": 10, "topic_id": self.tid}
        )
        self.assertEqual(response.status_code, 302)
        return response.location.rsplit("/", 1)[-1]

    def test_exam_delays_feedback_and_self_grading_until_finish(self):
        sid = self.make_exam()
        rows = self.rows(
            "SELECT * FROM session_items WHERE session_id=? ORDER BY position", (sid,)
        )
        other = self.other()
        self.assertEqual(other.get("/nauka/" + sid).status_code, 404)
        self.assertEqual(
            self.client.post("/nauka/" + sid + "/egzamin-odpowiedz").status_code, 400
        )
        for index, item in enumerate(rows):
            html = self.client.get("/nauka/" + sid).get_data(as_text=True)
            for secret in (
                "SECRET_MODEL_ANSWER",
                "SECRET_HINT",
                "SECRET_REASON",
                "SECRET_CRITERIA",
            ):
                self.assertNotIn(secret, html)
            self.assertEqual(
                self.post(
                    "/nauka/" + sid + "/odpowiedz",
                    {"item_id": item["id"], "response": "Right"},
                ).status_code,
                409,
            )
            self.assertEqual(
                self.post(
                    "/nauka/" + sid + "/ocena", {"item_id": item["id"], "grade": 3}
                ).status_code,
                409,
            )
            activity = json.loads(item["snapshot_json"])
            response = (
                "Wrong" if activity["kind"] == "quiz" else "My independent response"
            )
            self.assertEqual(
                self.post(
                    "/nauka/" + sid + "/egzamin-odpowiedz",
                    {"item_id": item["id"], "response": response},
                ).status_code,
                302,
            )
            if index == 0:
                self.assertEqual(len(self.rows("SELECT * FROM reviews")), 0)
        self.assertEqual(len(self.rows("SELECT * FROM reviews")), 1)
        html = self.client.get("/nauka/" + sid).get_data(as_text=True)
        self.assertIn("SECRET_MODEL_ANSWER", html)
        self.assertIn("SECRET_REASON", html)
        open_item = next(
            item for item in rows if json.loads(item["snapshot_json"])["kind"] == "open"
        )
        self.post("/nauka/" + sid + "/ocena", {"item_id": open_item["id"], "grade": 2})
        self.post("/nauka/" + sid + "/ocena", {"item_id": open_item["id"], "grade": 2})
        self.assertEqual(len(self.rows("SELECT * FROM reviews")), 2)
        self.assertEqual(
            self.post(
                "/nauka/" + sid + "/cofnij",
                {"review_id": self.rows("SELECT id FROM reviews")[-1]["id"]},
            ).status_code,
            409,
        )

    def test_paused_exam_does_not_reveal_answers(self):
        sid = self.make_exam()
        item = self.latest_item(sid)
        response = (
            "Right"
            if json.loads(item["snapshot_json"])["kind"] == "quiz"
            else "My answer"
        )
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {"item_id": item["id"], "response": response},
        )
        self.post("/nauka/" + sid + "/przerwa")
        html = self.client.get("/nauka/" + sid).get_data(as_text=True)
        self.assertIn("Przerwa zapisana", html)
        self.assertNotIn("SECRET_MODEL_ANSWER", html)
        self.assertEqual(len(self.rows("SELECT * FROM reviews")), 0)
        self.post("/nauka/" + sid + "/wznow")
        self.assertNotIn(
            "SECRET_MODEL_ANSWER",
            self.client.get("/nauka/" + sid).get_data(as_text=True),
        )

    def test_import_preview_is_owned_and_repeat_safe(self):
        data = [
            {
                "kind": "quiz",
                "prompt": "Imported quiz",
                "answer": "Right",
                "options": ["Wrong", "Right"],
                "explanation": "Imported explanation",
                "hints": ["Hint"],
                "minutes": 2,
            },
            {"kind": "flashcard", "prompt": "Card", "answer": "Back"},
        ]
        response = self.post(
            f"/tematy/{self.tid}/import-cwiczen",
            {"format": "json", "text": json.dumps(data)},
        )
        self.assertEqual(response.status_code, 302)
        path = response.location
        self.assertEqual(len(self.rows("SELECT * FROM activities")), 0)
        self.assertEqual(self.other().get(path).status_code, 404)
        self.assertEqual(self.client.post(path).status_code, 400)
        self.post(path)
        self.post(path)
        self.assertEqual(len(self.rows("SELECT * FROM activities")), 2)
        self.assertEqual(
            self.rows(
                "SELECT explanation FROM activity_support ORDER BY explanation DESC"
            )[0]["explanation"],
            "Imported explanation",
        )

    def test_import_tsv_csv_validation_and_no_partial_write(self):
        for format, text in [
            ("tsv", "Front\tBack\nAnother\tAnswer"),
            (
                "csv",
                'prompt,answer,kind,options\n"Question, quoted",Right,quiz,Wrong|Right',
            ),
        ]:
            response = self.post(
                f"/tematy/{self.tid}/import-cwiczen", {"format": format, "text": text}
            )
            self.assertEqual(response.status_code, 302)
            self.post(response.location)
        before = len(self.rows("SELECT * FROM activities"))
        for text in [
            '[{"prompt":"Good","answer":"Fine"},{"prompt":"Bad"}]',
            json.dumps([{"prompt": "Q", "answer": "A"}] * 201),
            "{bad}",
            '[{"kind":[],"prompt":"Q","answer":"A"}]',
            '[{"kind":{},"prompt":"Q","answer":"A"}]',
        ]:
            self.assertEqual(
                self.post(
                    f"/tematy/{self.tid}/import-cwiczen",
                    {"format": "json", "text": text},
                ).status_code,
                400,
            )
        self.assertEqual(len(self.rows("SELECT * FROM activities")), before)

    def test_safe_formatting_keeps_math_tables_and_code(self):
        html = str(
            render_content(
                "| A | B |\n|---|---|\n| 1 | 2 |\n\n$$x^2$$\n\n```python\nprint(42)\n```\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))\n\n![bad](https://example.test/image.png)"
            )
        )
        self.assertIn("<table>", html)
        self.assertIn("math block", html)
        self.assertIn("language-python", html)
        self.assertNotIn("<script>", html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn("<img", html)

    def test_hard_answer_shortens_existing_interval(self):
        from madra.services.learning import next_interval

        self.assertEqual(next_interval(8, 1), 4)
        self.assertEqual(next_interval(0, 1), 1)
        self.assertEqual(next_interval(8, 0), 1)

    def test_help_source_ownership_and_snapshot(self):
        self.post(
            f"/tematy/{self.tid}/materialy/nowy",
            {
                "kind": "note",
                "title": "Source",
                "content": "## First\nFirst chapter\n## Second\nSecond chapter",
            },
        )
        mid = self.rows("SELECT id FROM materials")[0]["id"]
        aid = self.activity()
        data = {
            "kind": "open",
            "prompt": "Source question",
            "answer": "Source answer",
            "minutes": 2,
            "material_id": mid,
            "source_chapter": 2,
            "hints": ["One", "Two"],
            "explanation": "Reason",
            "rubric": "Criterion",
        }
        self.post("/cwiczenia/" + aid + "/edytuj", data)
        sid, item = self.start()
        snapshot = json.loads(item["snapshot_json"])
        self.assertEqual(snapshot["source_chapter"], 2)
        self.assertEqual(snapshot["hints"], ["One", "Two"])
        self.assertIn(
            "#" + mid + "-chapter-2",
            self.client.get("/nauka/" + sid).get_data(as_text=True),
        )
        data["source_chapter"] = 99
        self.post("/cwiczenia/" + aid + "/edytuj", data)
        self.assertEqual(
            self.rows("SELECT source_chapter FROM activity_support")[0][
                "source_chapter"
            ],
            2,
        )

    def test_expand_saved_chapter_preserves_original_and_prior_materials(self):
        response = self.post(
            "/materialy/wgraj",
            {
                "file": (io.BytesIO(b"Synthetic source"), "source.txt"),
                "topic_id": self.tid,
            },
        )
        uid = response.location.rsplit("/", 1)[-1]
        draft = {
            "generator": "ai",
            "guide": "## First\nFirst chapter\n\n## Second\nSecond chapter",
            "title": "Source",
            "activities": [],
        }
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?", (json.dumps(draft), uid)
            )
        self.post("/pliki/" + uid, {"title": "Source", "guide": draft["guide"]})
        mid = self.rows("SELECT id FROM materials")[0]["id"]
        response = self.post(
            "/pliki/" + uid + "/rozbuduj", {"material_id": mid, "chapter": 2}
        )
        self.assertEqual(response.status_code, 302)
        repeated = self.post(
            "/pliki/" + uid + "/rozbuduj", {"material_id": mid, "chapter": 2}
        )
        self.assertEqual(response.location, repeated.location)
        nid = response.location.rsplit("/", 1)[-1]
        source = self.rows("SELECT * FROM uploads WHERE id=?", (nid,))[0]
        self.assertEqual(source["file_blob"], b"Synthetic source")
        self.assertEqual(json.loads(source["draft_json"])["focus"], "Second")
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,created_at) VALUES ('expansion-job',?,?,'running','synthetic','chapter',?)",
                (nid, self.uid, now_iso()),
            )
        from madra.ai import run_job

        generated = {
            "generator": "ai",
            "title": "Second chapter",
            "guide": "Expanded explanation",
            "activities": [],
        }
        with patch("madra.ai.generate", return_value=generated):
            run_job(
                self.app, "expansion-job", self.uid, nid, "synthetic", "Second chapter"
            )
        self.assertEqual(
            json.loads(
                self.rows("SELECT draft_json FROM uploads WHERE id=?", (nid,))[0][
                    "draft_json"
                ]
            )["parent_upload_id"],
            uid,
        )
        self.assertEqual(
            self.post(
                "/pliki/" + uid + "/rozbuduj", {"material_id": mid, "chapter": 2}
            ).location,
            response.location,
        )
        self.assertEqual(len(self.rows("SELECT * FROM materials")), 1)
        self.assertEqual(self.other().get("/pliki/" + nid + "/czytaj").status_code, 404)

    def test_export_and_account_deletion_include_student_tables(self):
        self.activity()
        self.goal([self.tid])
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        self.post(
            f"/tematy/{self.tid}/import-cwiczen", {"format": "tsv", "text": "Q\tA"}
        )
        payload = json.loads(self.client.get("/konto/eksport").data)
        for table in (
            "activity_support",
            "session_settings",
            "review_notes",
            "goal_settings",
            "goal_topics",
            "activity_imports",
        ):
            self.assertTrue(payload[table])
        self.assertEqual(
            self.post(
                "/konto/usun",
                {"current_password": "strong-pass-123", "confirm_username": "Alice"},
            ).status_code,
            302,
        )
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("PRAGMA foreign_key_check").fetchall(), []
            )
            for table in (
                "activity_support",
                "session_settings",
                "review_notes",
                "goal_settings",
                "goal_topics",
                "activity_imports",
            ):
                self.assertEqual(
                    get_db().execute("SELECT COUNT(*) FROM " + table).fetchone()[0], 0
                )

    def test_migration_from_schema_seven_preserves_existing_user(self):
        path = Path(self.directory.name) / "version-seven.sqlite3"
        db = sqlite3.connect(path)
        try:
            for migration in sorted(Path("madra/migrations").glob("00[1-7]*.sql")):
                db.executescript(migration.read_text())
            db.execute(
                "INSERT INTO users VALUES (?,?,?,0,?)",
                ("existing", "Existing", self.password_hash, now_iso()),
            )
            db.commit()
        finally:
            db.close()
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "DATABASE": str(path),
                "CLOUD_STATE_BUCKET": None,
            }
        )
        with app.app_context():
            self.assertEqual(get_db().execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertEqual(
                get_db().execute("SELECT username FROM users").fetchone()[0], "Existing"
            )


class StudentCloudTests(unittest.TestCase):
    setUp = cloud_fixtures.CloudTests.setUp
    tearDown = cloud_fixtures.CloudTests.tearDown
    make_app = cloud_fixtures.CloudTests.make_app
    post = cloud_fixtures.CloudTests.post

    def prepare_topic(self):
        wid = self.post(
            "/przedmioty/nowy", {"name": "Cloud course", "color": "blue"}
        ).location.rsplit("/", 1)[-1]
        return self.post(
            "/przedmioty/" + wid + "/tematy/nowy", {"name": "Cloud topic"}
        ).location.rsplit("/", 1)[-1]

    def test_import_exam_answers_and_self_rating_survive_restart(self):
        tid = self.prepare_topic()
        preview = self.post(
            "/tematy/" + tid + "/import-cwiczen",
            {"format": "tsv", "text": "Cloud question\tCloud model answer"},
        )
        self.post(preview.location, {})
        sid = self.post(
            "/nauka/start", {"topic_id": tid, "mode": "exam", "budget": 5}
        ).location.rsplit("/", 1)[-1]
        with self.app.app_context():
            item = (
                get_db()
                .execute("SELECT id FROM session_items WHERE session_id=?", (sid,))
                .fetchone()[0]
            )
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {"item_id": item, "response": "Cloud independent answer"},
        )
        restarted = self.make_app()
        client = restarted.test_client()
        with client.session_transaction() as session:
            session["user_id"] = self.uid
            session["csrf"] = "test"
        self.assertIn(
            "Cloud independent answer",
            client.get("/nauka/" + sid).get_data(as_text=True),
        )
        self.assertEqual(
            client.post(
                "/nauka/" + sid + "/ocena",
                data={"csrf_token": "test", "item_id": item, "grade": 1},
            ).status_code,
            302,
        )
        with self.make_app().app_context():
            self.assertEqual(
                get_db().execute("SELECT last_grade FROM progress").fetchone()[0], 1
            )
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM exam_answers").fetchone()[0], 1
            )
            self.assertEqual(
                get_db().execute("PRAGMA foreign_key_check").fetchall(), []
            )

    def test_cloud_import_failure_can_be_retried_without_duplicates(self):
        tid = self.prepare_topic()
        preview = self.post(
            "/tematy/" + tid + "/import-cwiczen",
            {"format": "tsv", "text": "Question\tAnswer"},
        )
        self.cloud.fail_write = True
        self.assertEqual(self.post(preview.location, {}).status_code, 503)
        self.cloud.fail_write = False
        self.post(preview.location, {})
        self.post(preview.location, {})
        with self.app.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM activities").fetchone()[0], 1
            )
