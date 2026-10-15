"""Exercise UX behavior: isolated data, atomic quiz results and scoped practice."""

import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_ai as ai_fixtures
from test_student_workflow import WorkflowFixture
from madra.db import transaction


class ExerciseWorkspaceTests(WorkflowFixture):
    def test_quiz_check_saves_once_and_feedback_keeps_variants(self):
        self.activity("quiz", answer="Right", options=["Wrong", "Right"])
        self.activity(prompt="Next question")
        sid, item = self.start()
        # Select the quiz explicitly, independently of scheduler ordering.
        quiz = next(
            r
            for r in self.rows("SELECT * FROM session_items")
            if json.loads(r["snapshot_json"])["kind"] == "quiz"
        )
        if quiz["id"] != item["id"]:
            self.reveal(sid, item)
            self.grade(sid, item)
        result = self.reveal(sid, quiz, "Wrong")
        self.assertIn("feedback=", result.location)
        quiz_reviews = self.rows("SELECT * FROM reviews WHERE item_id=?", (quiz["id"],))
        self.assertEqual(len(quiz_reviews), 1)
        self.assertEqual(
            (quiz_reviews[0]["grade"], quiz_reviews[0]["objective_correct"]), (0, 0)
        )
        page = self.client.get(result.location).get_data(as_text=True)
        self.assertIn("Niepoprawna odpowiedź", page)
        self.assertIn("is-incorrect", page)
        self.assertIn("Twój wybór", page)
        self.assertIn("Right", page)
        self.assertNotIn("Zapisz wynik i kontynuuj", page)
        retry = self.reveal(sid, quiz, "Right")
        self.assertEqual(retry.location, result.location)
        self.client.get(result.location)
        self.assertEqual(
            len(self.rows("SELECT * FROM reviews WHERE item_id=?", (quiz["id"],))), 1
        )
        self.assertEqual(
            self.rows("SELECT response FROM reviews WHERE item_id=?", (quiz["id"],))[0][
                "response"
            ],
            "Wrong",
        )

    def test_concurrent_quiz_checks_are_atomic_and_server_graded(self):
        self.activity("quiz", answer="Right", options=["Right", "Wrong"])
        sid, item = self.start()

        def check(response):
            client = self.app.test_client()
            self.authenticate(client)
            return self.post(
                "/nauka/" + sid + "/odpowiedz",
                {"item_id": item["id"], "response": response},
                client=client,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(check, ["Wrong", "Right"])), [302, 302])
        review = self.rows("SELECT * FROM reviews")[0]
        self.assertEqual(self.count("reviews"), 1)
        self.assertEqual(review["grade"], 2 if review["response"] == "Right" else 0)
        self.assertEqual(self.rows("SELECT reviews FROM progress")[0]["reviews"], 1)

    def test_failed_quiz_commit_rolls_back_reveal_and_progress(self):
        self.activity("quiz", answer="Right", options=["Right", "Wrong"])
        sid, item = self.start()
        with patch(
            "madra.study.finish_review", side_effect=RuntimeError("synthetic failure")
        ):
            with self.assertRaises(RuntimeError):
                self.reveal(sid, item, "Wrong")
        self.assertEqual(self.count("reviews"), 0)
        self.assertEqual(self.count("progress"), 0)
        self.assertEqual(
            self.rows("SELECT revealed FROM session_items")[0]["revealed"], 0
        )

    def test_atomic_quiz_can_be_undone_without_changing_frozen_attempt(self):
        self.activity("quiz", answer="Right", options=["Right", "Wrong"])
        sid, item = self.start()
        result = self.reveal(sid, item, "Wrong")
        review = self.rows("SELECT id FROM reviews")[0]["id"]
        self.post("/nauka/" + sid + "/cofnij", {"review_id": review})
        self.assertEqual(self.count("reviews"), 0)
        self.assertEqual(self.count("progress"), 0)
        self.assertEqual(self.client.get(result.location).status_code, 404)
        self.reveal(sid, item, "Right")
        self.grade(sid, item, 3)
        self.assertEqual(self.rows("SELECT grade FROM reviews")[0]["grade"], 0)

    def test_single_question_excludes_rest_and_rejects_foreign_or_archived(self):
        aid = self.activity(prompt="Only this question")
        self.activity(prompt="Never selected")
        other = self.other()
        self.assertEqual(
            self.post("/nauka/start", {"activity_id": aid}, client=other).status_code,
            404,
        )
        self.assertEqual(
            self.client.post("/nauka/start", data={"activity_id": aid}).status_code, 400
        )
        result = self.post("/nauka/start", {"topic_id": self.tid, "activity_id": aid})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            [
                r["activity_id"]
                for r in self.rows("SELECT activity_id FROM session_items")
            ],
            [aid],
        )
        sid = result.location.rsplit("/", 1)[-1]
        self.post("/nauka/" + sid + "/przerwa")
        self.post("/cwiczenia/" + aid + "/archiwizuj")
        self.assertEqual(
            self.post("/nauka/start", {"activity_id": aid}).status_code, 404
        )

    def test_single_question_scope_survives_active_session_switch(self):
        self.activity(prompt="First")
        sid, item = self.start()
        aid = self.activity(prompt="Second")
        conflict = self.post("/nauka/start", {"topic_id": self.tid, "activity_id": aid})
        self.assertEqual(conflict.status_code, 409)
        self.assertIn(
            ('name="activity_id" value="' + aid + '"').encode(), conflict.data
        )
        result = self.post(
            "/nauka/start",
            {"topic_id": self.tid, "activity_id": aid, "switch": "1", "active_id": sid},
        )
        new_sid = result.location.rsplit("/", 1)[-1]
        self.assertEqual(
            [
                r["activity_id"]
                for r in self.rows(
                    "SELECT activity_id FROM session_items WHERE session_id=?",
                    (new_sid,),
                )
            ],
            [aid],
        )
        self.assertEqual(
            self.rows("SELECT paused FROM session_settings WHERE session_id=?", (sid,))[
                0
            ]["paused"],
            1,
        )

    def test_skip_needs_no_fake_answer_and_cannot_count_as_independent_success(self):
        self.activity()
        sid, item = self.start()
        self.assertEqual(
            self.post(
                "/nauka/" + sid + "/odpowiedz",
                {"item_id": item["id"], "skip": "1", "revision": 0},
            ).status_code,
            302,
        )
        self.grade(sid, item, 3)
        self.assertEqual(self.rows("SELECT grade FROM reviews")[0]["grade"], 0)
        self.assertEqual(
            self.rows("SELECT used_help FROM review_notes")[0]["used_help"], 1
        )

    def test_preview_is_private_safe_and_does_not_modify_draft(self):
        uid = ai_fixtures.AITests.source(self)
        draft = ai_fixtures.validate_draft(ai_fixtures.draft())
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?", (json.dumps(draft), uid)
            )
        path = "/pliki/" + uid + "/podglad-cwiczenia"
        self.assertEqual(
            self.post(path, {"index": 0}, client=self.other()).status_code, 404
        )
        self.assertEqual(self.client.post(path, data={"index": 0}).status_code, 400)
        result = self.post(
            path,
            {
                "index": 0,
                "prompt": "Oblicz $x^2$.\n\n```python\nprint(2)\n```\n<script>alert(1)</script>",
            },
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"math inline", result.data)
        self.assertIn(b"<pre><code", result.data)
        self.assertNotIn(b"<script>", result.data)
        self.assertEqual(
            json.loads(
                self.rows("SELECT draft_json FROM uploads WHERE id=?", (uid,))[0][
                    "draft_json"
                ]
            ),
            draft,
        )
        self.assertEqual(self.post(path, {"index": -1}).status_code, 400)
        self.assertEqual(
            self.post(path, {"index": 0, "prompt": "x" * 10001}).status_code, 400
        )
