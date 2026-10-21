"""Student work is verified on isolated synthetic databases, never production."""

import base64
import io
import json
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4
from PIL import Image

import test_mvp as fixtures
from madra import create_app
from madra.db import get_db, transaction
from madra.services.learning import now_iso, today_date, activities_for
from madra.services.daily_plan import day_plan, week_plan
from madra.services.goals import nearest_goal
from madra.ai import run_job


class WorkflowFixture(unittest.TestCase):
    setUpClass = classmethod(fixtures.MVPTests.setUpClass.__func__)
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    authenticate = fixtures.MVPTests.authenticate
    post = fixtures.MVPTests.post
    activity = fixtures.MVPTests.activity
    start = fixtures.MVPTests.start
    reveal = fixtures.MVPTests.reveal
    grade = fixtures.MVPTests.grade
    count = fixtures.MVPTests.count

    def rows(self, sql, args=()):
        with self.app.app_context():
            return [dict(r) for r in get_db().execute(sql, args)]

    def other(self):
        client = self.app.test_client()
        self.post(
            "/register",
            {
                "username": "Another student",
                "email": "other@example.test",
                "password": "strong-pass-123",
                "confirm_password": "strong-pass-123",
            },
            client=client,
        )
        return client

    def goal(self, wid=None, title="Exam", days=3, minutes=30):
        with self.app.app_context():
            target = (today_date() + timedelta(days=days)).isoformat()
        self.post(
            "/cele/nowy",
            {
                "workspace_id": wid or self.wid,
                "title": title,
                "target_date": target,
                "daily_minutes": minutes,
            },
        )
        return self.rows("SELECT id FROM goals WHERE title=?", (title,))[0]["id"]

    def second_topic(self, other_course=False):
        wid = self.wid
        if other_course:
            wid = self.post(
                "/przedmioty/nowy", {"name": "Second course"}
            ).location.rsplit("/", 1)[-1]
        tid = self.post(
            "/przedmioty/" + wid + "/tematy/nowy", {"name": "Second topic"}
        ).location.rsplit("/", 1)[-1]
        return wid, tid

    def note(self, content="## First\n\nCore idea.\n\n## Second\n\nAnother idea."):
        self.post(
            "/tematy/" + self.tid + "/materialy/nowy",
            {"kind": "note", "title": "Lecture", "content": content},
        )
        return self.rows("SELECT id FROM materials")[0]["id"]

    def image(self, color="blue"):
        output = io.BytesIO()
        Image.new("RGB", (32, 24), color).save(output, format="PNG")
        return output.getvalue()


class WorkflowTests(WorkflowFixture):
    def test_draft_survives_pause_refresh_restart_without_review(self):
        self.activity()
        sid, item = self.start()
        response = self.post(
            "/nauka/" + sid + "/szkic",
            {"item_id": item["id"], "response": "Unfinished reasoning", "revision": 0},
        )
        self.assertEqual(response.json, {"revision": 1})
        self.assertEqual(self.count("reviews"), 0)
        self.assertEqual(
            self.rows("SELECT revealed FROM session_items")[0]["revealed"], 0
        )
        self.post(
            "/nauka/" + sid + "/przerwa",
            {"item_id": item["id"], "response": "A longer draft", "revision": 1},
        )
        self.post("/nauka/" + sid + "/wznow")
        self.assertIn(b"A longer draft", self.client.get("/nauka/" + sid).data)
        restarted = create_app(
            {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": self.path}
        )
        with restarted.app_context():
            self.assertEqual(
                get_db().execute("SELECT response FROM study_drafts").fetchone()[0],
                "A longer draft",
            )

    def test_stale_draft_and_final_submit_do_not_overwrite(self):
        self.activity()
        sid, item = self.start()
        fields = {"item_id": item["id"], "response": "First tab", "revision": 0}
        self.assertEqual(self.post("/nauka/" + sid + "/szkic", fields).status_code, 200)
        fields["response"] = "Stale tab"
        self.assertEqual(self.post("/nauka/" + sid + "/szkic", fields).status_code, 409)
        self.assertEqual(
            self.post("/nauka/" + sid + "/odpowiedz", fields).status_code, 409
        )
        self.assertEqual(
            self.rows("SELECT response FROM study_drafts")[0]["response"], "First tab"
        )

    def test_drafts_require_ownership_and_csrf(self):
        self.activity()
        sid, item = self.start()
        other = self.other()
        self.assertIn(
            self.post(
                "/nauka/" + sid + "/szkic",
                {"item_id": item["id"], "response": "Intrusion"},
                client=other,
            ).status_code,
            (404, 409),
        )
        self.assertEqual(
            self.client.post(
                "/nauka/" + sid + "/szkic", data={"item_id": item["id"]}
            ).status_code,
            400,
        )
        self.assertEqual(self.count("study_drafts"), 0)

    def test_quiz_draft_restores_selection_and_rejects_unknown_option(self):
        self.activity("quiz", answer="Right", options=["Right", "Wrong"])
        sid, item = self.start()
        self.assertEqual(
            self.post(
                "/nauka/" + sid + "/szkic",
                {"item_id": item["id"], "response": "Wrong", "revision": 0},
            ).status_code,
            200,
        )
        page = self.client.get("/nauka/" + sid).get_data(as_text=True)
        self.assertIn('value="Wrong" checked', page)
        self.assertEqual(
            self.post(
                "/nauka/" + sid + "/szkic",
                {"item_id": item["id"], "response": "Unknown", "revision": 1},
            ).status_code,
            400,
        )

    def test_paper_response_and_hint_usage_are_saved(self):
        self.activity()
        sid, item = self.start()
        self.post(
            "/nauka/" + sid + "/szkic",
            {
                "item_id": item["id"],
                "response": "",
                "response_mode": "paper",
                "used_help": "1",
                "revision": 0,
            },
        )
        self.post(
            "/nauka/" + sid + "/odpowiedz",
            {"item_id": item["id"], "response_mode": "paper", "revision": 1},
        )
        self.grade(sid, item)
        self.assertIn(
            "kartce", self.rows("SELECT response FROM reviews")[0]["response"]
        )
        self.assertEqual(
            self.rows("SELECT used_help FROM review_notes")[0]["used_help"], 1
        )

    def test_note_draft_is_restored_and_removed_after_final_save(self):
        key = "newnote:" + self.tid
        fields = {
            "draft_key": key,
            "draft_revision": 0,
            "title": "Draft title",
            "content": "Not finished",
            "kind": "note",
        }
        self.assertEqual(self.post("/szkice/notatki", fields).status_code, 200)
        self.assertIn(
            b"Not finished",
            self.client.get("/tematy/" + self.tid + "/materialy/nowy").data,
        )
        self.assertEqual(self.post("/szkice/notatki", fields).status_code, 409)
        fields.update(draft_revision=1)
        self.post("/tematy/" + self.tid + "/materialy/nowy", fields)
        self.assertEqual(self.count("form_drafts"), 0)
        self.assertEqual(
            self.rows("SELECT content FROM materials")[0]["content"], "Not finished"
        )

    def test_quick_note_recall_and_offline_download(self):
        response = self.post(
            "/notatki/nowa",
            {"title": "New lecture", "content": "## Mechanism\n\nImportant material."},
        )
        self.assertEqual(response.status_code, 302)
        mid = response.location.rsplit("/", 1)[-1]
        page = self.client.get("/notatki/" + mid + "/cwicz?stage=recall").data
        self.assertNotIn(b"Important material.", page)
        self.post("/notatki/" + mid + "/cwicz", {"chapter": 1, "response": "My memory"})
        self.assertEqual(
            self.rows("SELECT completed FROM reading_progress")[0]["completed"], 1
        )
        self.assertEqual(self.count("reviews"), 0)
        offline = self.client.get("/notatki/" + mid + "/pobierz")
        self.assertIn(b"Important material.", offline.data)
        self.assertNotIn(b"<script", offline.data)

    def test_source_note_is_preselected_and_reading_position_owned(self):
        mid = self.note()
        page = self.client.get(
            "/tematy/" + self.tid + "/cwiczenia/nowe?material_id=" + mid + "&chapter=2"
        ).data
        self.assertIn(('value="' + mid + '" selected').encode(), page)
        self.assertEqual(
            self.post("/notatki/" + mid + "/pozycja", {"chapter": 2}).status_code, 200
        )
        self.assertIn(
            b'data-last-chapter="2"', self.client.get("/materialy/" + mid).data
        )
        self.assertEqual(
            self.post("/notatki/" + mid + "/pozycja", {"chapter": 99}).status_code, 400
        )
        self.assertEqual(
            self.post(
                "/notatki/" + mid + "/pozycja", {"chapter": 1}, client=self.other()
            ).status_code,
            404,
        )

    def test_daily_plan_shares_one_allowance_between_goals_and_excludes_expired(self):
        self.activity(minutes=2)
        wid, tid = self.second_topic(True)
        self.post(
            "/tematy/" + tid + "/cwiczenia/nowe",
            {
                "kind": "open",
                "prompt": "Second course question",
                "answer": "Answer",
                "minutes": 2,
            },
        )
        first = self.goal(title="First exam")
        self.goal(wid, title="Second exam", days=4)
        expired = self.goal(title="Old exam")
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE goals SET target_date=? WHERE id=?",
                ((today_date() - timedelta(days=1)).isoformat(), expired),
            )
        self.post("/plan/czas", {"budget": 5})
        with self.app.app_context():
            plan = day_plan(self.uid, 5)
            self.assertEqual(len(plan["allocations"]), 2)
            self.assertLessEqual(plan["minutes"], 5)
            self.assertEqual(nearest_goal(self.uid)["id"], first)
            self.assertTrue(all(d["minutes"] <= 5 for d in week_plan(self.uid)))
        page = self.client.get("/dzisiaj").get_data(as_text=True)
        self.assertIn('name="budget" type="number" min="1" max="180" value="5"', page)
        self.assertIn("Old exam", page)
        response = self.post("/nauka/start", {"budget": 5})
        sid = response.location.rsplit("/", 1)[-1]
        self.assertEqual(
            len(self.rows("SELECT * FROM session_items WHERE session_id=?", (sid,))), 2
        )

    def test_global_difficult_action_includes_errors_outside_nearest_goal(self):
        self.activity()
        wid, tid = self.second_topic(True)
        self.post(
            "/tematy/" + tid + "/cwiczenia/nowe",
            {
                "kind": "open",
                "prompt": "Hard elsewhere",
                "answer": "Answer",
                "minutes": 1,
            },
        )
        self.goal()
        response = self.post("/nauka/start", {"topic_id": tid, "budget": 5})
        sid = response.location.rsplit("/", 1)[-1]
        item = self.rows("SELECT * FROM session_items WHERE session_id=?", (sid,))[0]
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        page = self.client.get("/dzisiaj").get_data(as_text=True)
        self.assertIn("mode=difficult&amp;all=1", page)
        response = self.post(
            "/nauka/start", {"mode": "difficult", "global_scope": "1", "budget": 5}
        )
        self.assertNotEqual(response.location, "/biblioteka")
        self.assertIn(b"Hard elsewhere", self.client.get(response.location).data)

    def test_goal_scope_and_days_can_be_set_on_creation(self):
        _, second = self.second_topic()
        with self.app.app_context():
            day = str(today_date().weekday())
        self.post(
            "/cele/nowy",
            {
                "workspace_id": self.wid,
                "title": "Scoped",
                "target_date": "2030-01-01",
                "daily_minutes": 20,
                "schedule_configured": "1",
                "weekdays": [day],
                "topic_ids": [second],
            },
        )
        self.assertEqual(self.count("goal_topics"), 1)
        self.assertEqual(
            self.rows("SELECT topic_id FROM goal_topics")[0]["topic_id"], second
        )

    def test_archiving_course_keeps_history_and_excludes_new_plans(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item)
        self.post("/porzadek/workspace/" + self.wid + "/status", {"action": "archive"})
        with self.app.app_context():
            self.assertEqual(activities_for(self.uid), [])
        self.assertIn(b"Explain energy", self.client.get("/nauka/" + sid).data)
        self.assertEqual(self.count("reviews"), 1)
        self.post("/porzadek/workspace/" + self.wid + "/status", {"action": "restore"})
        with self.app.app_context():
            self.assertEqual(len(activities_for(self.uid)), 1)

    def test_material_trash_hides_it_and_linked_exercises_until_restore(self):
        mid = self.note()
        aid = self.activity()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE activity_support SET material_id=? WHERE activity_id=?",
                (mid, aid),
            )
        self.post("/porzadek/material/" + mid + "/status", {"action": "trash"})
        with self.app.app_context():
            self.assertEqual(activities_for(self.uid), [])
        self.post("/porzadek/material/" + mid + "/status", {"action": "restore"})
        with self.app.app_context():
            self.assertEqual(len(activities_for(self.uid)), 1)

    def test_move_exercise_clears_incompatible_source_and_keeps_history(self):
        mid = self.note()
        aid = self.activity()
        _, tid = self.second_topic()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE activity_support SET material_id=? WHERE activity_id=?",
                (mid, aid),
            )
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item)
        self.post("/porzadek/activity/" + aid + "/przenies", {"destination": tid})
        self.assertIsNone(
            self.rows("SELECT material_id FROM activity_support")[0]["material_id"]
        )
        self.assertEqual(self.count("reviews"), 1)
        self.assertEqual(
            self.rows("SELECT topic_id FROM activities")[0]["topic_id"], tid
        )

    def test_cross_user_move_and_archive_are_rejected(self):
        other = self.other()
        self.assertEqual(
            self.post(
                "/porzadek/topic/" + self.tid + "/przenies",
                {"destination": self.wid},
                client=other,
            ).status_code,
            404,
        )
        self.assertEqual(
            self.post(
                "/porzadek/workspace/" + self.wid + "/status",
                {"action": "archive"},
                client=other,
            ).status_code,
            404,
        )
        self.assertEqual(self.count("content_states"), 0)

    def test_exam_navigation_edits_and_does_not_leak_answers_until_finish(self):
        self.activity("open", answer="SECRET_MODEL_ANSWER")
        self.activity(
            "quiz", prompt="A quiz", answer="Right", options=["Right", "Wrong"]
        )
        response = self.post(
            "/nauka/start",
            {
                "mode": "exam",
                "exam_count": 2,
                "timer_minutes": 10,
                "budget": 10,
                "global_scope": "1",
            },
        )
        sid = response.location.rsplit("/", 1)[-1]
        items = self.rows(
            "SELECT * FROM session_items WHERE session_id=? ORDER BY position", (sid,)
        )
        open_item = next(
            i for i in items if json.loads(i["snapshot_json"])["kind"] == "open"
        )
        quiz = next(i for i in items if i["id"] != open_item["id"])
        page = self.client.get("/nauka/" + sid + "?item=" + open_item["id"]).data
        self.assertNotIn(b"SECRET_MODEL_ANSWER", page)
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {
                "item_id": open_item["id"],
                "response": "Partial",
                "revision": 0,
                "go_to": quiz["id"],
                "flagged": "1",
            },
        )
        self.assertEqual(self.count("exam_answers"), 0)
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {"item_id": quiz["id"], "response": "Wrong", "revision": 0},
        )
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {"item_id": quiz["id"], "response": "Right", "revision": 1},
        )
        self.post(
            "/nauka/" + sid + "/egzamin-odpowiedz",
            {
                "item_id": open_item["id"],
                "response": "Final explanation",
                "revision": 1,
            },
        )
        self.assertEqual(self.count("reviews"), 0)
        self.assertNotIn(b"SECRET_MODEL_ANSWER", self.client.get("/nauka/" + sid).data)
        self.post("/nauka/" + sid + "/zakoncz")
        self.assertIn(b"SECRET_MODEL_ANSWER", self.client.get("/nauka/" + sid).data)
        self.assertEqual(self.rows("SELECT grade FROM reviews")[0]["grade"], 2)

    def test_exam_count_can_include_long_tasks_without_time_bias(self):
        long_aid = self.activity("exercise", prompt="Long problem", minutes=15)
        for i in range(3):
            self.activity(prompt="Question " + str(i), minutes=1)
        response = self.post(
            "/nauka/start",
            {"mode": "exam", "exam_count": 4, "budget": 5, "global_scope": "1"},
        )
        sid = response.location.rsplit("/", 1)[-1]
        ids = {
            r["activity_id"]
            for r in self.rows("SELECT * FROM session_items WHERE session_id=?", (sid,))
        }
        self.assertIn(long_aid, ids)

    def test_image_is_private_and_frozen_after_edit(self):
        aid = self.activity()
        self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "open",
                "prompt": "Diagram question",
                "answer": "Answer",
                "minutes": 2,
                "question_image": (io.BytesIO(self.image()), "diagram.png"),
            },
        )
        sid, item = self.start()
        old = json.loads(item["snapshot_json"])["image_id"]
        self.assertEqual(self.client.get("/obrazy/" + old).status_code, 200)
        self.assertEqual(self.other().get("/obrazy/" + old).status_code, 404)
        self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "open",
                "prompt": "Changed",
                "answer": "Answer",
                "minutes": 2,
                "question_image": (io.BytesIO(self.image("red")), "new.png"),
            },
        )
        self.assertIn(old.encode(), self.client.get("/nauka/" + sid).data)
        self.assertEqual(self.client.get("/obrazy/" + old).status_code, 200)

    def test_batch_upload_is_atomic_and_images_supported(self):
        response = self.post(
            "/materialy/wgraj",
            {
                "file": [
                    (io.BytesIO(b"Notes"), "notes.txt"),
                    (io.BytesIO(b"bad"), "bad.exe"),
                ]
            },
        )
        self.assertIn("Wybierz", response.get_data(as_text=True))
        self.assertEqual(self.count("uploads"), 0)
        response = self.post(
            "/materialy/wgraj",
            {
                "file": [
                    (io.BytesIO(b"Notes"), "notes.txt"),
                    (io.BytesIO(self.image()), "diagram.png"),
                ]
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.count("uploads"), 2)

    def test_requirements_are_explicit_and_owned(self):
        gid = self.goal()
        self.post(
            "/cele/" + gid + "/wymagania",
            {"titles": "Bayes theorem\nIndependence", "topic_id": self.tid},
        )
        self.assertEqual(self.count("goal_requirements"), 2)
        rid = self.rows("SELECT id FROM goal_requirements")[0]["id"]
        self.assertEqual(
            self.post(
                "/cele/" + gid + "/wymagania",
                {"requirement_id": rid},
                client=self.other(),
            ).status_code,
            404,
        )
        self.post("/cele/" + gid + "/wymagania", {"requirement_id": rid})
        self.assertEqual(
            sum(
                r["checked"] for r in self.rows("SELECT checked FROM goal_requirements")
            ),
            1,
        )

    def test_topic_package_roundtrip_preview_and_repeat_save(self):
        self.note()
        self.activity()
        package = self.client.get("/tematy/" + self.tid + "/eksport-zestawu").json
        self.assertNotIn("reviews", package)
        before = self.count("topics")
        response = self.post("/zestawy/import", {"text": json.dumps(package)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.count("topics"), before)
        preview = response.location
        saved = self.post(preview)
        self.post(preview)
        self.assertEqual(self.count("topics"), before + 1)
        self.assertEqual(self.count("activities"), 2)
        self.assertEqual(self.count("reviews"), 0)
        self.assertEqual(self.other().get(preview).status_code, 404)
        self.assertEqual(self.client.get(saved.location).status_code, 200)

    def test_cancelled_ai_worker_cannot_overwrite_or_change_cancellation(self):
        self.post("/materialy/wgraj", {"file": (io.BytesIO(b"Notes"), "notes.txt")})
        uid = self.rows("SELECT id FROM uploads")[0]["id"]
        jid = uuid4().hex
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,error,created_at) VALUES (?,?,?,'running','model','goal','',?)",
                (jid, uid, self.uid, now_iso()),
            )
        draft = {"guide": "new output", "activities": [], "generator": "ai"}

        def generate(*args, **kwargs):
            self.post("/ai/zadania/" + jid + "/anuluj")
            return draft

        with patch("madra.ai.generate", side_effect=generate):
            run_job(self.app, jid, self.uid, uid, "model", "goal")
        row = self.rows("SELECT * FROM ai_jobs")[0]
        self.assertIn("Anulowano", row["error"])
        self.assertEqual(
            json.loads(self.rows("SELECT draft_json FROM uploads")[0]["draft_json"])[
                "generator"
            ],
            "pending",
        )

    def test_export_includes_new_data_without_raw_binary_or_credentials(self):
        self.note()
        self.activity()
        sid, item = self.start()
        self.post(
            "/nauka/" + sid + "/szkic", {"item_id": item["id"], "response": "Draft"}
        )
        result = self.client.get("/konto/eksport").json
        for key in (
            "study_drafts",
            "form_drafts",
            "daily_preferences",
            "content_states",
            "reading_progress",
            "goal_requirements",
            "image_assets",
            "topic_packages",
        ):
            self.assertIn(key, result)
        self.assertNotIn("password_hash", json.dumps(result))

    def test_optional_repeat_is_bounded_and_waits_for_other_questions(self):
        for i in range(4):
            self.activity(prompt="Question " + str(i), minutes=1)
        response = self.post("/nauka/start", {"budget": 10, "repeat_errors": "1"})
        sid = response.location.rsplit("/", 1)[-1]
        item = self.rows("SELECT * FROM session_items ORDER BY position")[0]
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        self.assertEqual(self.count("session_items"), 5)
        self.grade(sid, item, 0)
        self.assertEqual(self.count("session_items"), 5)
        last = self.rows("SELECT * FROM session_items ORDER BY position DESC")[0]
        self.assertEqual(last["activity_id"], item["activity_id"])

    def test_migration_from_eight_preserves_sessions_and_history(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item)
        with self.app.app_context():
            db = get_db()
            for table in (
                "study_drafts",
                "form_drafts",
                "daily_preferences",
                "content_states",
                "reading_progress",
                "goal_requirements",
                "activity_images",
                "image_assets",
                "exam_options",
                "topic_packages",
            ):
                db.execute("DROP TABLE " + table)
            db.execute("PRAGMA user_version=8")
        upgraded = create_app(
            {"TESTING": True, "SECRET_KEY": "test-secret", "DATABASE": self.path}
        )
        with upgraded.app_context():
            self.assertEqual(get_db().execute("PRAGMA user_version").fetchone()[0], 9)
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 1
            )
            self.assertEqual(
                get_db().execute("PRAGMA foreign_key_check").fetchall(), []
            )


class WorkflowEdgeTests(WorkflowFixture):
    """Additional cases use the same temporary fixtures without inheriting tests."""

    def test_daily_plan_same_titles_have_separate_caps_and_maximum_thirty(self):
        self.activity(prompt="Course one", minutes=3)
        wid, tid = self.second_topic(True)
        self.post(
            "/tematy/" + tid + "/cwiczenia/nowe",
            {"kind": "open", "prompt": "Course two", "answer": "Answer", "minutes": 3},
        )
        self.goal(title="Same title", minutes=5)
        with self.app.app_context():
            today = today_date()
            with transaction() as db:
                db.execute(
                    "INSERT INTO goals VALUES (?,?,?,?,?,?,0,?)",
                    (
                        uuid4().hex,
                        self.uid,
                        wid,
                        "Same title",
                        (today + timedelta(days=4)).isoformat(),
                        5,
                        now_iso(),
                    ),
                )
            plan = day_plan(self.uid, 10)
        self.assertEqual(len(plan["items"]), 2)
        for i in range(35):
            self.activity(prompt="Extra " + str(i), minutes=1)
        with self.app.app_context(), transaction() as db:
            db.execute("UPDATE goals SET daily_minutes=180")
        with self.app.app_context():
            self.assertLessEqual(len(day_plan(self.uid, 180)["items"]), 30)

    def test_overlap_does_not_duplicate_plan_or_week_workload(self):
        self.activity(minutes=2)
        self.goal(title="First")
        self.goal(title="Second")
        with self.app.app_context():
            self.assertEqual(len(day_plan(self.uid, 20)["items"]), 1)
            self.assertEqual(sum(d["minutes"] for d in week_plan(self.uid)), 2)

    def test_used_minutes_reduce_default_daily_portion(self):
        self.activity(minutes=2)
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item)
        self.post("/plan/czas", {"budget": 5})
        self.assertIn(
            'name="budget" type="number" min="1" max="180" value="3"',
            self.client.get("/dzisiaj").get_data(as_text=True),
        )

    def test_recall_draft_is_owned_and_does_not_complete_reading(self):
        mid = self.note()
        key = "recall:" + mid + ":1"
        self.assertEqual(
            self.post(
                "/szkice/notatki",
                {
                    "draft_key": key,
                    "draft_revision": 0,
                    "response": "My unfinished recall",
                },
            ).status_code,
            200,
        )
        self.assertIn(
            b"My unfinished recall",
            self.client.get("/notatki/" + mid + "/cwicz?stage=recall").data,
        )
        self.assertEqual(self.count("reading_progress"), 0)
        self.assertEqual(
            self.post(
                "/szkice/notatki",
                {"draft_key": key, "response": "Other user"},
                client=self.other(),
            ).status_code,
            404,
        )
        self.post(
            "/notatki/" + mid + "/cwicz",
            {"chapter": 1, "response": "My finished recall", "draft_revision": 1},
        )
        self.assertEqual(self.count("form_drafts"), 0)

    def test_delete_account_removes_drafts_images_reading_and_packages(self):
        mid = self.note()
        self.activity()
        sid, item = self.start()
        self.post(
            "/nauka/" + sid + "/szkic", {"item_id": item["id"], "response": "A draft"}
        )
        self.post("/notatki/" + mid + "/pozycja", {"chapter": 1})
        self.post(
            "/zestawy/import",
            {
                "text": json.dumps(
                    {
                        "format": "madra-topic-1",
                        "title": "Imported",
                        "materials": [
                            {"kind": "note", "title": "Note", "content": "Text"}
                        ],
                        "activities": [],
                    }
                )
            },
        )
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO image_assets VALUES (?,?,?,?)",
                (uuid4().hex, self.uid, self.image(), now_iso()),
            )
        response = self.post(
            "/konto/usun",
            {"current_password": "strong-pass-123", "confirm_username": "Alice"},
        )
        self.assertEqual(response.status_code, 302)
        for table in (
            "users",
            "study_drafts",
            "image_assets",
            "reading_progress",
            "topic_packages",
        ):
            self.assertEqual(self.count(table), 0)

    def test_move_topic_detaches_requirements_from_old_course(self):
        gid = self.goal()
        wid, tid = self.second_topic(True)
        self.post(
            "/cele/" + gid + "/wymagania",
            {"titles": "A requirement", "topic_id": self.tid},
        )
        rid = self.rows("SELECT id FROM goal_requirements")[0]["id"]
        self.post("/cele/" + gid + "/wymagania", {"requirement_id": rid})
        self.post("/porzadek/topic/" + self.tid + "/przenies", {"destination": wid})
        requirement = self.rows("SELECT * FROM goal_requirements")[0]
        self.assertIsNone(requirement["topic_id"])
        self.assertEqual(requirement["checked"], 0)
        self.assertEqual(
            self.rows("SELECT workspace_id FROM topics WHERE id=?", (self.tid,))[0][
                "workspace_id"
            ],
            wid,
        )

    def test_topic_package_image_roundtrip_and_rejects_unsafe_material_link(self):
        data = {
            "format": "madra-topic-1",
            "title": "Pictures",
            "materials": [],
            "activities": [
                {
                    "kind": "open",
                    "prompt": "Describe",
                    "answer": "Explanation",
                    "image_png": base64.b64encode(self.image()).decode(),
                }
            ],
        }
        preview = self.post("/zestawy/import", {"text": json.dumps(data)}).location
        self.post(preview)
        self.assertEqual(self.count("activity_images"), 1)
        data["materials"] = [
            {"kind": "link", "title": "Unsafe", "content": "javascript:alert(1)"}
        ]
        result = self.post("/zestawy/import", {"text": json.dumps(data)})
        self.assertIn("Nieprawidłowy link", result.get_data(as_text=True))

    def test_correct_quiz_choice_is_selected_by_index(self):
        aid = self.activity("quiz", answer="Right", options=["Right", "Wrong"])
        result = self.post(
            "/cwiczenia/" + aid + "/edytuj",
            {
                "kind": "quiz",
                "prompt": "Question",
                "options": "Wrong\nRight",
                "correct_option": "1",
                "answer": "Ignored duplicate field",
                "minutes": 1,
            },
        )
        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            self.rows("SELECT answer FROM activities")[0]["answer"], "Right"
        )

    def test_generated_image_uses_vision_input_and_preset(self):
        from madra.services.ai_materials import generate
        from test_ai import draft

        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(draft())},
            {"type": "response.completed"},
        ]
        response = io.BytesIO(
            b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
        )
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=response
            ) as network,
        ):
            generate(
                self.uid, "image.png", self.image(), "model", "[SZYBKA POWTÓRKA] Topic"
            )
        payload = json.loads(network.call_args.args[0].data)
        self.assertEqual(payload["input"][0]["content"][0]["type"], "input_image")
        self.assertIn("6000", payload["instructions"])


class PlanningRegressionTests(WorkflowFixture):
    def test_remaining_short_budget_can_start(self):
        self.activity(minutes=2)
        result = self.post("/nauka/start", {"budget": 3})
        self.assertEqual(result.status_code, 302)
        self.assertIn("/nauka/", result.location)

    def test_switch_between_daily_and_all_scope_is_explicit(self):
        self.activity()
        self.goal()
        sid, _ = self.start()
        conflict = self.post("/nauka/start", {"budget": 10, "global_scope": "1"})
        self.assertEqual(conflict.status_code, 409)
        result = self.post(
            "/nauka/start",
            {"budget": 10, "global_scope": "1", "switch": "1", "active_id": sid},
        )
        self.assertEqual(result.status_code, 302)
        self.assertNotEqual(result.location, "/nauka/" + sid)

    def test_method_filter_is_applied_before_thirty_item_limit(self):
        for i in range(31):
            self.activity(
                "quiz",
                prompt="Quiz " + str(i),
                answer="Yes",
                options=["Yes", "No"],
                minutes=1,
            )
        long_aid = self.activity("exercise", prompt="Long exercise", minutes=10)
        self.goal(minutes=180)
        result = self.post("/nauka/start", {"budget": 20, "kinds": ["exercise"]})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            [r["activity_id"] for r in self.rows("SELECT * FROM session_items")],
            [long_aid],
        )

    def test_cancel_stops_consuming_the_stream_and_keeps_draft(self):
        from madra.services.ai_materials import generate

        response = io.BytesIO(b'data: {"type":"response.created"}\n\n')
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch("madra.services.ai_materials.urlopen", return_value=response),
        ):
            with self.assertRaisesRegex(ValueError, "anulowane"):
                generate(
                    self.uid,
                    "material.txt",
                    b"Material",
                    "model",
                    "Goal",
                    is_cancelled=lambda: True,
                )
        self.assertTrue(response.closed)


class CloudDraftTests(unittest.TestCase):
    from test_cloud import CloudTests as _Fixture

    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    make_app = _Fixture.make_app
    post = _Fixture.post

    def test_cloud_retry_preserves_draft_revision_without_creating_reviews(self):
        self.post("/przedmioty/nowy", {"name": "Course"})
        with self.app.app_context():
            wid = get_db().execute("SELECT id FROM workspaces").fetchone()[0]
        self.post("/przedmioty/" + wid + "/tematy/nowy", {"name": "Topic"})
        with self.app.app_context():
            tid = get_db().execute("SELECT id FROM topics").fetchone()[0]
        self.post(
            "/tematy/" + tid + "/cwiczenia/nowe",
            {"kind": "open", "prompt": "Question", "answer": "Model", "minutes": 2},
        )
        sid = self.post("/nauka/start", {"budget": 10}).location.rsplit("/", 1)[-1]
        with self.app.app_context():
            iid = get_db().execute("SELECT id FROM session_items").fetchone()[0]
        fields = {"item_id": iid, "revision": 0, "response": "Cloud draft"}
        self.cloud.fail_write = True
        self.assertEqual(self.post("/nauka/" + sid + "/szkic", fields).status_code, 503)
        self.cloud.fail_write = False
        self.assertEqual(
            self.post("/nauka/" + sid + "/szkic", fields).json, {"revision": 1}
        )
        restarted = self.make_app()
        with restarted.app_context():
            row = (
                get_db()
                .execute("SELECT response,revision FROM study_drafts")
                .fetchone()
            )
            self.assertEqual(tuple(row), ("Cloud draft", 1))
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 0
            )


class DailyAllocationTests(WorkflowFixture):
    def test_allocation_labels_totals_and_per_goal_limit(self):
        for i in range(10):
            self.activity(prompt="Question " + str(i), minutes=1)
        self.goal(title="Readable exam title", minutes=5)
        with self.app.app_context():
            plan = day_plan(self.uid, 20)
        self.assertEqual(plan["minutes"], 5)
        self.assertEqual(plan["allocations"], {"Readable exam title": 5})
        self.assertEqual(
            sum(plan["allocations"].values()), sum(a["minutes"] for a in plan["items"])
        )


class ExamFinishTests(WorkflowFixture):
    def test_finish_confirmation_is_read_only_counts_answers_and_hides_models(self):
        self.activity(answer="SECRET_EXPLANATION")
        result = self.post(
            "/nauka/start", {"mode": "exam", "exam_count": 1, "budget": 10}
        )
        sid = result.location.rsplit("/", 1)[-1]
        page = self.client.get("/nauka/" + sid + "/zakoncz")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b"SECRET_EXPLANATION", page.data)
        self.assertIn("Pytania bez wyniku: 1.", page.get_data(as_text=True))
        self.assertEqual(
            self.rows("SELECT status FROM study_sessions")[0]["status"], "active"
        )
        self.assertEqual(
            self.other().get("/nauka/" + sid + "/zakoncz").status_code, 404
        )


class RetryCorrectionTests(WorkflowFixture):
    def test_undo_removes_unanswered_retry_and_regrade_can_queue_it_once(self):
        for i in range(4):
            self.activity(prompt="Question " + str(i), minutes=1)
        result = self.post("/nauka/start", {"budget": 10, "repeat_errors": "1"})
        sid = result.location.rsplit("/", 1)[-1]
        item = self.rows("SELECT * FROM session_items ORDER BY position")[0]
        self.reveal(sid, item)
        self.grade(sid, item, 0)
        review = self.rows("SELECT id FROM reviews")[0]["id"]
        self.assertEqual(self.count("session_items"), 5)
        self.post("/nauka/" + sid + "/cofnij", {"review_id": review})
        self.assertEqual(self.count("session_items"), 4)
        self.grade(sid, item, 2)
        self.assertEqual(self.count("session_items"), 4)


class MaterialLifecycleTests(WorkflowFixture):
    def generated_upload(self):
        result = self.post(
            "/materialy/wgraj",
            {
                "topic_id": self.tid,
                "file": (io.BytesIO(b"Source lecture"), "lecture.txt"),
            },
        )
        uid = result.location.rsplit("/", 1)[-1]
        draft = {
            "generator": "ai",
            "guide": "AI guide",
            "activities": [
                {
                    "kind": "open",
                    "prompt": "Explain a mechanism",
                    "answer": "Model explanation",
                    "minutes": 2,
                    "label": "Source section",
                    "options": [],
                }
            ],
        }
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?", (json.dumps(draft), uid)
            )
        return uid

    def test_save_questions_without_duplicate_note(self):
        uid = self.generated_upload()
        fields = {
            "title": "Topic",
            "guide": "AI guide",
            "note_choice": "1",
            "selected": ["0"],
            "prompt_0": "Explain a mechanism",
            "answer_0": "Model explanation",
        }
        result = self.post("/pliki/" + uid, fields)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.count("materials"), 0)
        self.assertEqual(self.count("activities"), 1)
        self.post("/pliki/" + uid, fields)
        self.assertEqual(self.count("activities"), 1)
        self.assertEqual(self.client.get("/pliki/" + uid).status_code, 200)

    def test_trash_uploaded_work_hides_note_questions_and_counts_then_restores(self):
        uid = self.generated_upload()
        fields = {
            "title": "Unique AI note",
            "guide": "AI guide",
            "selected": ["0"],
            "prompt_0": "Explain a mechanism",
            "answer_0": "Model explanation",
        }
        self.post("/pliki/" + uid, fields)
        self.post("/porzadek/upload/" + uid + "/status", {"action": "trash"})
        self.assertNotIn(b"Unique AI note", self.client.get("/tematy/" + self.tid).data)
        self.assertNotIn(
            b"Unique AI note", self.client.get("/biblioteka?q=Unique").data
        )
        with self.app.app_context():
            self.assertEqual(activities_for(self.uid), [])
        self.post("/porzadek/upload/" + uid + "/status", {"action": "restore"})
        self.assertIn(b"Unique AI note", self.client.get("/tematy/" + self.tid).data)
        with self.app.app_context():
            self.assertEqual(len(activities_for(self.uid)), 1)


class ReviewDatePlanTests(WorkflowFixture):
    def test_week_does_not_schedule_good_answers_before_due_date(self):
        self.activity()
        sid, item = self.start()
        self.reveal(sid, item)
        self.grade(sid, item, 2)
        self.goal(days=7)
        with self.app.app_context():
            week = week_plan(self.uid)
        self.assertEqual(sum(d["minutes"] for d in week[:3]), 0)
        self.assertGreater(week[3]["minutes"], 0)
