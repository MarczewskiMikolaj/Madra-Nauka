"""Cloud durability, concurrent writes and OAuth relay use only synthetic data."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from google.api_core.exceptions import NotFound, PreconditionFailed
from madra import create_app
from madra.db import get_db, transaction
from madra.services import chatgpt
from madra.services.cloud_state import CloudState, StateConflict


class FakeClient:
    def __init__(self):
        self.objects = {}
        self.serial = 0
        self.fail_write = False

    def bucket(self, name):
        return self

    def blob(self, name):
        client = self

        class Blob:
            generation = None

            def reload(self, **kwargs):
                if name not in client.objects:
                    raise NotFound("Missing")
                self.generation = client.objects[name][1]

            def download_as_bytes(self, if_generation_match, **kwargs):
                data, generation = client.objects[name]
                if generation != if_generation_match:
                    raise PreconditionFailed("Stale read")
                return data

            def upload_from_string(self, data, if_generation_match, **kwargs):
                if client.fail_write:
                    raise RuntimeError("Synthetic unavailable storage")
                generation = client.objects.get(name, (None, 0))[1]
                if if_generation_match != generation:
                    raise PreconditionFailed("Stale write")
                client.serial += 1
                client.objects[name] = (data, client.serial)
                self.generation = client.serial

            def delete(self, if_generation_match, **kwargs):
                if name not in client.objects:
                    raise NotFound("Missing")
                if client.objects[name][1] != if_generation_match:
                    raise PreconditionFailed("Stale lock")
                del client.objects[name]

        return Blob()


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.cloud = FakeClient()
        self.app = self.make_app()
        self.client = self.app.test_client()
        self.post(
            "/register",
            {
                "username": "CloudStudent",
                "password": "test-password-123",
                "confirm_password": "test-password-123",
            },
        )
        with self.client.session_transaction() as session:
            self.uid = session["user_id"]

    def tearDown(self):
        self.directory.cleanup()

    def make_app(self):
        with patch(
            "madra.services.cloud_state.CloudState",
            side_effect=lambda bucket, prefix: CloudState(bucket, prefix, self.cloud),
        ):
            return create_app(
                {
                    "TESTING": True,
                    "DATABASE": str(
                        Path(self.directory.name) / "never-written.sqlite3"
                    ),
                    "SECRET_KEY": "synthetic-secret",
                    "CLOUD_STATE_BUCKET": "fake",
                    "PUBLIC_URL": "https://madranauka.online",
                }
            )

    def post(self, path, data):
        with self.client.session_transaction() as session:
            session["csrf"] = "test-csrf"
        return self.client.post(path, data={"csrf_token": "test-csrf", **data})

    def test_account_upload_and_encrypted_connection_survive_new_instance(self):
        response = self.post(
            "/materialy/wgraj",
            {
                "file": (
                    io.BytesIO(
                        b"Synthetic source material with educational knowledge."
                    ),
                    "cloud.txt",
                )
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            with chatgpt.locked(self.uid):
                chatgpt.load(self.uid)
                chatgpt.save(self.uid, {"tokens": {"access_token": "synthetic-token"}})
        self.assertNotIn(
            b"synthetic-token",
            self.cloud.objects["madra-v2/auth/" + self.uid + ".enc"][0],
        )
        restarted = self.make_app()
        with restarted.app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0], 1
            )
            self.assertEqual(
                get_db().execute("SELECT file_blob FROM uploads").fetchone()[0],
                b"Synthetic source material with educational knowledge.",
            )
            self.assertEqual(
                chatgpt.load(self.uid)["tokens"]["access_token"], "synthetic-token"
            )
        self.assertFalse(Path(self.app.config["DATABASE"]).exists())

    def test_stale_revision_cannot_overwrite_newer_committed_data(self):
        other = self.make_app()
        with self.app.app_context():
            with self.assertRaises(StateConflict):
                with transaction() as db:
                    db.execute(
                        "INSERT INTO workspaces VALUES ('lost',?,'Lost','','blue','now',NULL)",
                        (self.uid,),
                    )
                    with other.app_context(), transaction() as second:
                        second.execute(
                            "INSERT INTO workspaces VALUES ('kept',?,'Kept','','blue','now',NULL)",
                            (self.uid,),
                        )
        with other.app_context():
            self.assertEqual(
                [row[0] for row in get_db().execute("SELECT id FROM workspaces")],
                ["kept"],
            )

    def test_failed_cloud_write_does_not_report_a_successful_upload(self):
        self.cloud.fail_write = True
        response = self.post(
            "/materialy/wgraj",
            {"file": (io.BytesIO(b"Synthetic educational material."), "failed.txt")},
        )
        self.assertEqual(response.status_code, 503)
        self.cloud.fail_write = False
        with self.make_app().app_context():
            self.assertEqual(
                get_db().execute("SELECT COUNT(*) FROM uploads").fetchone()[0], 0
            )

    def test_cloud_oauth_relay_preserves_local_callback_and_requires_csrf(self):
        page = self.client.get("/konto/ai")
        self.assertIn(b"madra-login.py", page.data)
        helper = self.client.get("/konto/ai/pomocnik")
        self.assertIn(b"127.0.0.1", helper.data)
        self.assertIn(b"https://madranauka.online/konto/ai/powrot", helper.data)
        self.assertIn(b'"#"', helper.data)
        self.assertNotIn(b"api_key", helper.data)
        compile(helper.get_data(as_text=True), "helper.py", "exec")
        with self.app.app_context():
            url = chatgpt.begin(self.uid, self.app.config["CHATGPT_CALLBACK_URL"])
            self.assertIn("127.0.0.1%3A8085%2Fauth%2Fcallback", url)
            pending = chatgpt.load(self.uid)["pending"]
        self.assertEqual(
            self.client.post(
                "/konto/ai/powrot", data={"state": pending["state"]}
            ).status_code,
            400,
        )
        with patch(
            "madra.ai.chatgpt.finish",
            return_value={
                "tokens": {"scope": "chatgpt.tokens.use.direct", "access_token": "test"}
            },
        ) as finish:
            response = self.post(
                "/konto/ai/powrot", {"code": "test-code", "state": pending["state"]}
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(finish.call_args.args[1]["state"], pending["state"])

    def test_export_does_not_include_credential_objects(self):
        with self.app.app_context():
            chatgpt.load(self.uid)
            chatgpt.save(self.uid, {"tokens": {"access_token": "synthetic-token"}})
        data = json.loads(self.client.get("/konto/eksport").data)
        self.assertNotIn("synthetic-token", json.dumps(data))


if __name__ == "__main__":
    unittest.main()
