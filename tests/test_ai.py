import base64
import io
import json
import ssl
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from urllib.error import HTTPError, URLError

import test_mvp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from madra.ai import run_job
from madra.db import get_db, transaction
from madra.services import chatgpt
from madra.services.ai_materials import generate, validate_draft, stream_error
from madra.services.learning import now_iso
from madra.services.notes import note_chapters, content_title

TEXT = "Fotosynteza przekształca energię światła w energię chemiczną związków organicznych."


def draft():
    return {
        "title": "Fotosynteza",
        "guide": "Energia światła jest magazynowana w związkach organicznych.\nPrzykład: roślina rosnąca przy świetle.",
        "activities": [
            {
                "kind": "open",
                "prompt": "Jak zmienia się postać energii w fotosyntezie?",
                "answer": "Energia światła zmienia się w energię chemiczną.",
                "evidence": TEXT,
                "label": "Tekst",
                "minutes": 2,
            },
            {
                "kind": "quiz",
                "prompt": "Co dostarcza energii?",
                "answer": "Światło",
                "options": ["Światło", "Dźwięk", "Grawitacja"],
                "evidence": TEXT,
                "label": "Tekst",
                "minutes": 1,
            },
        ],
    }


class AITests(unittest.TestCase):
    setUpClass = classmethod(test_mvp.MVPTests.setUpClass.__func__)
    setUp = test_mvp.MVPTests.setUp
    tearDown = test_mvp.MVPTests.tearDown
    authenticate = test_mvp.MVPTests.authenticate
    post = test_mvp.MVPTests.post
    count = test_mvp.MVPTests.count

    def test_topic_creation_validation_and_owner(self):
        fields = {
            "source_mode": "topic",
            "subject": "SQL",
            "goal": "Pisać zapytania",
            "language": "en",
            "style": "technical",
            "workspace_id": self.wid,
        }
        for override in (
            {"subject": ""},
            {"goal": ""},
            {"language": "xx"},
            {"style": "unknown"},
        ):
            response = self.post("/materialy/wgraj", {**fields, **override})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.count("uploads"), 0)
        with self.app.app_context():
            self.connection()
        with (
            patch("madra.ai.chatgpt.models", return_value=[{"id": "gpt-5.6-terra"}]),
            patch("madra.ai.threading.Thread.start"),
        ):
            response = self.post("/materialy/wgraj", fields)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ai/zadania/", response.location)
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM uploads").fetchone()
            metadata = json.loads(row["draft_json"])
            self.assertEqual(metadata["source_mode"], "topic")
            self.assertEqual(metadata["style"], "technical")
            self.assertEqual(row["workspace_id"], self.wid)
        page = self.client.get("/pliki/" + row["id"]).get_data(as_text=True)
        self.assertNotIn('name="language"', page)
        self.assertIn("Zobacz postęp", page)
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE ai_jobs SET state='failed' WHERE upload_id=?", (row["id"],)
            )
        page = self.client.get("/pliki/" + row["id"]).get_data(as_text=True)
        self.assertNotIn('name="goal"', page)
        self.assertIn("Wróć do formularza i wygeneruj plan", page)
        retry = self.client.get("/materialy/wgraj?draft_id=" + row["id"]).get_data(
            as_text=True
        )
        self.assertIn('value="SQL"', retry)
        self.assertIn('value="en" selected', retry)
        self.assertIn('value="technical" selected', retry)
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO users VALUES ('other','Other',?,0,'now')",
                (self.password_hash,),
            )
        self.authenticate(self.client, "other")
        self.assertEqual(self.client.get(response.location).status_code, 404)
        self.assertEqual(self.client.get("/pliki/" + row["id"]).status_code, 404)
        self.assertEqual(self.post("/materialy/wgraj", fields).status_code, 404)

    def test_topic_requires_connection_without_losing_form(self):
        response = self.post(
            "/materialy/wgraj",
            {
                "source_mode": "topic",
                "subject": "SQL",
                "goal": "Pisać zapytania",
                "language": "en",
                "style": "technical",
            },
        )
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Połącz ChatGPT przed przygotowaniem materiałów", page)
        self.assertIn('value="SQL"', page)
        self.assertIn("Pisać zapytania", page)
        self.assertEqual(self.count("uploads"), 0)
        self.assertEqual(self.count("ai_jobs"), 0)

    def test_topic_stream_uses_text_and_selected_preferences(self):
        from madra.services.ai_materials import generate_topic

        value = draft()
        del value["guide"]
        value["chapters"] = [
            {"title": "SQL queries", "content": "Use SELECT to read rows."}
        ]
        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(value)},
            {"type": "response.completed"},
        ]
        response = io.BytesIO(
            b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
        )
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=response
            ) as opened,
        ):
            result = generate_topic(
                self.uid,
                "SQL",
                "model",
                "Learn SELECT",
                language="en",
                style="technical",
            )
        payload = json.loads(opened.call_args.args[0].data)
        content = payload["input"][0]["content"]
        self.assertEqual([c["type"] for c in content], ["input_text"])
        self.assertIn("SQL", content[0]["text"])
        self.assertIn("angielski", payload["instructions"])
        self.assertIn("Technicznie", payload["instructions"])
        self.assertIn("Nie ma załączonego źródła", payload["instructions"])
        self.assertIn("SQL queries", result["guide"])
        self.assertEqual(result["source_mode"], "topic")

    def test_topic_job_preserves_preferences_and_saves_to_library(self):
        with self.app.app_context():
            self.connection()

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        result = {**validate_draft(draft()), "source_mode": "topic"}
        with (
            patch(
                "madra.ai.chatgpt.models",
                return_value=[{"id": "gpt-5.6-terra", "name": "Terra"}],
            ),
            patch("madra.ai.generate_topic", return_value=result) as generator,
            patch("madra.ai.generate") as file_generator,
            patch("madra.ai.threading.Thread", ImmediateThread),
        ):
            response = self.post(
                "/materialy/wgraj",
                {
                    "source_mode": "topic",
                    "subject": "Fotosynteza",
                    "goal": "Zrozumieć proces",
                    "language": "en",
                    "style": "technical",
                    "topic_id": self.tid,
                },
            )
        self.assertIn("/ai/zadania/", response.location)
        with self.app.app_context():
            uid = get_db().execute("SELECT upload_id FROM ai_jobs").fetchone()[0]
        file_generator.assert_not_called()
        self.assertEqual(generator.call_args.args[1], "Fotosynteza")
        self.assertEqual(generator.call_args.kwargs["language"], "en")
        self.assertEqual(generator.call_args.kwargs["style"], "technical")
        with self.app.app_context():
            metadata = json.loads(
                get_db()
                .execute("SELECT draft_json FROM uploads WHERE id=?", (uid,))
                .fetchone()[0]
            )
        self.assertEqual(metadata["source_mode"], "topic")
        self.assertEqual(metadata["subject"], "Fotosynteza")
        with patch(
            "madra.ai.chatgpt.models",
            return_value=[{"id": "gpt-5.6-terra", "name": "Terra"}],
        ):
            page = self.client.get("/pliki/" + uid).get_data(as_text=True)
        self.assertIn("Uzasadnienie z notatki AI", page)
        self.assertNotIn("Fragment źródła wskazany przez AI", page)
        self.assertNotIn('name="preset"', page)
        self.assertNotIn('name="language"', page)
        response = self.post(
            "/pliki/" + uid, {"title": result["title"], "guide": result["guide"]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/tematy/", response.location)
        self.assertEqual(self.count("materials"), 1)

    def test_stream_errors_preserve_codes_in_all_event_shapes(self):
        code = "subscription_sharing_usage_limit_exceeded"
        for event in [
            {"type": "error", "code": code, "message": "Usage limit"},
            {"type": "response.failed", "response": {"error": {"code": code}}},
            {"type": "error", "error": {"code": code}},
        ]:
            self.assertIn(code, str(stream_error(event)))
            self.assertIn("limit", str(stream_error(event)))
        self.assertIn(
            "max_output_tokens",
            str(
                stream_error(
                    {
                        "type": "response.incomplete",
                        "response": {
                            "incomplete_details": {"reason": "max_output_tokens"}
                        },
                    }
                )
            ),
        )

    def test_https_verifies_certificates_and_hostname(self):
        context = chatgpt.tls_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_network_error_logging_excludes_credentials(self):
        endpoint = chatgpt.AUTH + "/api/accounts/oauth/token?code=secret-code"
        with self.app.app_context():
            with (
                patch(
                    "madra.services.chatgpt.urlopen",
                    side_effect=URLError(ssl.SSLCertVerificationError("secret-detail")),
                ),
                self.assertLogs(self.app.logger, level="WARNING") as logs,
            ):
                with self.assertRaisesRegex(ValueError, "certyfikatu HTTPS"):
                    chatgpt.fetch_json(endpoint, {"code": "secret-code"}, form=True)
            self.assertIn("SSLCertVerificationError", str(logs.output))
            self.assertNotIn("secret", str(logs.output))
            with (
                patch(
                    "madra.services.chatgpt.urlopen",
                    side_effect=HTTPError(endpoint, 400, "secret-detail", {}, None),
                ),
                self.assertLogs(self.app.logger, level="WARNING") as logs,
            ):
                with self.assertRaisesRegex(ValueError, "HTTP 400"):
                    chatgpt.fetch_json(endpoint)
            self.assertIn("status=400", str(logs.output))
            self.assertNotIn("secret", str(logs.output))

    def test_callback_access_log_hides_code(self):
        with patch("madra.create_app"):
            import app as server
        handler = object.__new__(server.PrivateRequestHandler)
        handler.path = "/auth/callback?code=secret-code&state=secret-state"
        handler.command, handler.request_version = "GET", "HTTP/1.1"
        with patch.object(handler, "log") as log:
            handler.log_request(302)
        self.assertNotIn("secret", str(log.call_args))
        self.assertIn("/auth/callback", str(log.call_args))
        self.assertIn("secret-code", handler.path)

    def source(self):
        response = self.post(
            "/materialy/wgraj",
            {
                "file": (
                    io.BytesIO(
                        (
                            TEXT
                            + " Chlorofil pochłania światło niezbędne do tego procesu."
                        ).encode()
                    ),
                    "nauka.txt",
                ),
                "topic_id": self.tid,
            },
        )
        return response.location.rsplit("/", 1)[-1]

    def connection(self):
        chatgpt.save(
            self.uid,
            {
                "allow_plan_and_credits": True,
                "client_id": "test-client",
                "subject": "test-sub",
                "email": "test@example.com",
                "expires_at": time.time() + 3600,
                "tokens": {
                    "access_token": "synthetic-token",
                    "refresh_token": "synthetic-refresh",
                    "scope": "openid chatgpt.tokens.use.direct",
                },
            },
        )

    def test_connection_starts_without_local_consent_checkbox(self):
        with patch(
            "madra.ai.chatgpt.begin", return_value="https://auth.openai.com/test"
        ) as begin:
            response = self.post("/konto/ai/polacz", {})
            self.assertEqual(response.location, "https://auth.openai.com/test")
            begin.assert_called_once()
        page = self.client.get("/konto/ai").get_data(as_text=True)
        self.assertNotIn("usage_consent", page)
        self.assertNotIn("Wspólna pula", page)

    def test_authorization_pkce_and_secret_storage(self):
        with self.app.app_context():
            url = chatgpt.begin(self.uid, "http://127.0.0.1:8081/auth/callback")
            params = parse_qs(urlparse(url).query)
            record = chatgpt.load(self.uid)
            self.assertEqual(params["client_id"], ["dynamic_agent_client"])
            self.assertEqual(params["code_challenge_method"], ["S256"])
            self.assertNotIn(record["pending"]["verifier"], url)
            raw = (chatgpt.directory() / (self.uid + ".enc")).read_bytes()
            self.assertNotIn(record["pending"]["verifier"].encode(), raw)
            self.assertEqual(
                (chatgpt.directory() / (self.uid + ".enc")).stat().st_mode & 0o777,
                0o600,
            )
            other = chatgpt.begin("other-user", "http://127.0.0.1:8081/auth/callback")
            self.assertEqual(
                params["ext_agent_host_id"],
                parse_qs(urlparse(other).query)["ext_agent_host_id"],
            )

    def test_callback_invalid_state_no_network(self):
        with self.app.app_context():
            chatgpt.begin(self.uid, "http://127.0.0.1:8081/auth/callback")
        with patch("madra.services.chatgpt.fetch_json") as fetch:
            self.client.get("/auth/callback?state=wrong&code=bad&client_id=fake")
            fetch.assert_not_called()
        with self.app.app_context():
            self.assertIn("pending", chatgpt.load(self.uid))

    def test_callback_scope_replay_and_returning_client(self):
        with self.app.app_context():
            chatgpt.begin(self.uid, "http://127.0.0.1:8081/auth/callback")
            state = chatgpt.load(self.uid)["pending"]["state"]
            args = {
                "state": state,
                "code": "synthetic-code",
                "client_id": "test-client",
            }
            with (
                patch(
                    "madra.services.chatgpt.fetch_json",
                    return_value={
                        "id_token": "fake",
                        "access_token": "fake-access",
                        "scope": "openid",
                        "expires_in": 3600,
                    },
                ),
                patch(
                    "madra.services.chatgpt.verify_identity",
                    return_value={"sub": "test-sub", "email": "test@example.com"},
                ),
            ):
                record = chatgpt.finish(self.uid, args)
            self.assertFalse(chatgpt.permitted(record))
            with self.assertRaises(ValueError):
                chatgpt.finish(self.uid, args)
            params = parse_qs(
                urlparse(
                    chatgpt.begin(self.uid, "http://127.0.0.1:8081/auth/callback")
                ).query
            )
            self.assertEqual(params["client_id"], ["test-client"])
            self.assertNotIn("agent_name_hint", params)

    def test_jwt_signature_nonce_issuer_and_audience(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = key.public_key().public_numbers()

        def enc(data):
            return base64.urlsafe_b64encode(data).decode().rstrip("=")

        jwk = {
            "kid": "test",
            "kty": "RSA",
            "n": enc(numbers.n.to_bytes(256, "big")),
            "e": enc(numbers.e.to_bytes(3, "big")),
        }

        def token(claims):
            header = enc(json.dumps({"alg": "RS256", "kid": "test"}).encode())
            body = enc(json.dumps(claims).encode())
            signed = header + "." + body
            return (
                signed
                + "."
                + enc(key.sign(signed.encode(), padding.PKCS1v15(), hashes.SHA256()))
            )

        claims = {
            "iss": chatgpt.AUTH,
            "aud": "test-client",
            "sub": "test-sub",
            "exp": time.time() + 1000,
            "nonce": "nonce",
        }
        with patch(
            "madra.services.chatgpt.fetch_json",
            side_effect=lambda url: (
                {"jwks_uri": chatgpt.AUTH + "/jwks"}
                if "well-known" in url
                else {"keys": [jwk]}
            ),
        ):
            self.assertEqual(
                chatgpt.verify_identity(token(claims), "test-client", "nonce")["sub"],
                "test-sub",
            )
            for change in [
                {"nonce": "wrong"},
                {"iss": "https://evil.example"},
                {"aud": "other"},
                {"exp": 1},
            ]:
                with self.assertRaises(ValueError):
                    chatgpt.verify_identity(
                        token({**claims, **change}), "test-client", "nonce"
                    )
            with self.assertRaises(ValueError):
                chatgpt.verify_identity(
                    token(claims)[:-5] + "abcde", "test-client", "nonce"
                )

    def test_refresh_rotates_credentials(self):
        with self.app.app_context():
            self.connection()
            record = chatgpt.load(self.uid)
            record["expires_at"] = 1
            chatgpt.save(self.uid, record)
            with patch(
                "madra.services.chatgpt.fetch_json",
                return_value={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                },
            ):
                self.assertEqual(chatgpt.access_token(self.uid), "new-access")
            self.assertEqual(
                chatgpt.load(self.uid)["tokens"]["refresh_token"], "new-refresh"
            )

    def test_draft_validation_source_reference_and_quiz(self):
        self.assertEqual(validate_draft(draft())["generator"], "ai")
        for key, value in [
            ("kind", "unknown"),
            ("evidence", ""),
            ("answer", ""),
        ]:
            bad = draft()
            bad["activities"][0][key] = value
            with self.assertRaises(ValueError):
                validate_draft(bad)
        bad = draft()
        bad["activities"][1]["answer"] = "Nie ma takiej opcji"
        with self.assertRaises(ValueError):
            validate_draft(bad)

    def test_generation_derives_plan_from_chapters_when_model_omits_order(self):
        value = draft()
        del value["guide"]
        value["chapters"] = [
            {"title": "Światło", "content": "## Energia\n\nŚwiatło dostarcza energii."},
            {"title": "Chlorofil", "content": "Chlorofil pochłania światło."},
        ]
        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(value)},
            {"type": "response.completed"},
        ]
        response = io.BytesIO(
            b"".join(
                b"data: " + json.dumps(event).encode() + b"\n\n" for event in events
            )
        )
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch("madra.services.ai_materials.urlopen", return_value=response),
        ):
            generated = generate(
                self.uid, "material.txt", TEXT.encode(), "model", "Nauka"
            )
        chapters = note_chapters(generated["guide"])
        self.assertEqual([c["title"] for c in chapters], ["Światło", "Chlorofil"])
        self.assertIn("### Energia", chapters[0]["content"])

    def test_stream_requires_completion_and_subscription_contract(self):
        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(draft())},
            {"type": "response.completed"},
        ]

        def stream(items):
            return io.BytesIO(
                b"".join(
                    b"data: " + json.dumps(item).encode() + b"\n\n" for item in items
                )
            )

        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=stream(events)
            ) as open_request,
        ):
            result = generate(
                self.uid, "material.txt", TEXT.encode(), "available-model", "Nauka"
            )
            self.assertEqual(result["generator"], "ai")
            payload = json.loads(open_request.call_args.args[0].data)
            self.assertTrue(payload["stream"])
            self.assertFalse(payload["store"])
            self.assertIsInstance(payload["input"], list)
            self.assertNotIn("max_output_tokens", payload)
            content = payload["input"][0]["content"]
            self.assertEqual(content[0]["type"], "input_file")
            self.assertEqual(content[0]["filename"], "material.txt")
            self.assertEqual(
                base64.b64decode(content[0]["file_data"].split(",", 1)[1]),
                TEXT.encode(),
            )
            self.assertNotIn(TEXT, content[1]["text"])
            self.assertEqual(result["source_mode"], "file")
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=stream(events[:1])
            ),
        ):
            with self.assertRaisesRegex(ValueError, "przerwano"):
                generate(
                    self.uid, "material.txt", TEXT.encode(), "available-model", "Nauka"
                )

    def test_original_pdf_preserves_pages_and_visual_sources(self):
        from pypdf import PdfWriter

        pdf = PdfWriter()
        pdf.add_blank_page(width=600, height=800)
        pdf.add_blank_page(width=600, height=800)
        document = io.BytesIO()
        pdf.write(document)
        result = draft()
        result["activities"][0]["label"] = "Strona 2, diagram"
        result["activities"][0]["evidence"] = "Diagram przedstawia przepływ energii."
        events = [
            {"type": "response.output_text.delta", "delta": json.dumps(result)},
            {"type": "response.completed"},
        ]
        response = io.BytesIO(
            b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
        )
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=response
            ) as opened,
        ):
            generated = generate(
                self.uid, "scan.pdf", document.getvalue(), "model", "Diagramy"
            )
        attachment = json.loads(opened.call_args.args[0].data)["input"][0]["content"][0]
        self.assertEqual(attachment["detail"], "high")
        self.assertEqual(attachment["filename"], "scan.pdf")
        self.assertEqual(
            base64.b64decode(attachment["file_data"].split(",", 1)[1]),
            document.getvalue(),
        )
        self.assertEqual(generated["activities"][0]["label"], "Strona 2, diagram")

    def test_progress_reports_real_stream_events_without_time_limit(self):
        events = [
            {"type": "response.created"},
            {"type": "response.output_text.delta", "delta": json.dumps(draft())},
            {"type": "response.completed"},
        ]
        response = io.BytesIO(
            b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
        )
        updates = []
        with (
            patch("madra.services.ai_materials.access_token", return_value="synthetic"),
            patch(
                "madra.services.ai_materials.urlopen", return_value=response
            ) as opened,
            patch("madra.services.ai_materials.time.monotonic", return_value=999999),
        ):
            generate(
                self.uid,
                "notes.txt",
                TEXT.encode(),
                "model",
                "Nauka",
                on_progress=lambda stage, chars: updates.append((stage, chars)),
            )
        self.assertIsNone(opened.call_args.kwargs["timeout"])
        self.assertEqual(
            [stage for stage, chars in updates],
            ["sending", "analyzing", "writing", "validating"],
        )
        self.assertEqual(updates[-1][1], len(json.dumps(draft())))

    def test_running_job_displays_persisted_progress(self):
        uid = self.source()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,error,created_at,progress_json) VALUES ('progress-job',?,?,'running','model','goal','',?,?)",
                (
                    uid,
                    self.uid,
                    now_iso(),
                    json.dumps({"stage": "writing", "output_chars": 1200}),
                ),
            )
        page = self.client.get("/ai/zadania/progress-job")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"1200", page.data)
        self.assertIn("Bez limitu czasu".encode(), page.data)
        self.assertIn(b'aria-current="step"', page.data)

    def test_job_failure_preserves_old_draft(self):
        uid = self.source()
        with self.app.app_context(), transaction() as db:
            before = db.execute(
                "SELECT draft_json FROM uploads WHERE id=?", (uid,)
            ).fetchone()[0]
            db.execute(
                "INSERT INTO ai_jobs (id,upload_id,user_id,state,model,goal,error,created_at,finished_at) VALUES ('job',?,?,'running','model','goal','',?,NULL)",
                (uid, self.uid, now_iso()),
            )
        with patch("madra.ai.generate", side_effect=ValueError("Limit planu")):
            run_job(self.app, "job", self.uid, uid, "model", "goal")
        with self.app.app_context():
            self.assertEqual(
                get_db()
                .execute("SELECT draft_json FROM uploads WHERE id=?", (uid,))
                .fetchone()[0],
                before,
            )
            self.assertEqual(
                get_db()
                .execute("SELECT state FROM ai_jobs WHERE id='job'")
                .fetchone()[0],
                "failed",
            )
        page = self.client.get("/pliki/" + uid)
        self.assertIn(b"Limit planu", page.data)
        self.assertIn("Ostatnie opracowanie nie zostało ukończone".encode(), page.data)
        self.assertIn("Błąd opracowania".encode(), self.client.get("/biblioteka").data)

    def test_preview_list_preserves_original_order_and_activity_indexes(self):
        source = self.source()
        result = draft()
        result["activities"].insert(
            0,
            {
                "kind": "flashcard",
                "prompt": "Czym jest chlorofil?",
                "answer": "Barwnikiem pochłaniającym światło.",
                "evidence": TEXT,
                "label": "Tekst",
                "minutes": 1,
            },
        )
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?",
                (
                    json.dumps(validate_draft(result)),
                    source,
                ),
            )
        page = self.client.get("/pliki/" + source).get_data(as_text=True)
        self.assertLess(
            page.index('data-exercise-kind="flashcard"'),
            page.index('data-exercise-kind="open"'),
        )
        self.assertIn('name="prompt_0"', page)
        self.assertIn('name="prompt_2"', page)
        fields = {
            "title": result["title"],
            "guide": result["guide"],
            "selected": ["0", "2"],
        }
        for i, item in enumerate(result["activities"]):
            fields["prompt_" + str(i)] = item["prompt"]
            fields["answer_" + str(i)] = item["answer"]
            if item["kind"] == "quiz":
                fields["options_" + str(i)] = "\n".join(item["options"])
        response = self.post("/pliki/" + source, fields)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            saved = (
                get_db()
                .execute(
                    "SELECT kind,prompt,answer FROM activities WHERE topic_id=?",
                    (self.tid,),
                )
                .fetchall()
            )
            self.assertEqual(
                {(row["kind"], row["prompt"], row["answer"]) for row in saved},
                {
                    (item["kind"], item["prompt"], item["answer"])
                    for item in [result["activities"][0], result["activities"][2]]
                },
            )
        topic = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('data-exercise-kind="quiz"', topic)
        self.assertIn('data-exercise-kind="flashcard"', topic)
        self.assertNotIn('data-exercise-kind="open"', topic)

    def test_ai_chapters_survive_save_and_are_readable_after_import(self):
        source = self.source()
        value = draft()
        del value["guide"]
        value["chapters"] = [
            {
                "title": "Energia światła",
                "content": "Światło dostarcza energii do procesu.",
            },
            {
                "title": "Chlorofil i jego rola",
                "content": "Chlorofil pochłania światło. <script>alert(1)</script>",
            },
        ]
        result = validate_draft(value)
        self.assertEqual(note_chapters(result["guide"]), value["chapters"])
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?",
                (json.dumps(result), source),
            )
        page = self.client.get("/pliki/" + source).get_data(as_text=True)
        self.assertIn("Spis treści", page)
        self.assertIn('id="draft-chapter-2"', page)
        self.assertNotIn("<script>alert(1)</script>", page)
        response = self.post(
            "/pliki/" + source,
            {"title": result["title"], "guide": result["guide"], "selected": []},
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            mid = (
                get_db()
                .execute(
                    "SELECT material_id FROM upload_materials WHERE upload_id=?",
                    (source,),
                )
                .fetchone()[0]
            )
        saved_page = self.client.get("/pliki/" + source).get_data(as_text=True)
        self.assertIn("Czytaj notatkę", saved_page)
        self.assertIn("Chlorofil i jego rola", saved_page)
        reader = self.client.get("/materialy/" + mid)
        self.assertEqual(reader.status_code, 200)
        self.assertIn("Spis treści".encode(), reader.data)
        self.assertIn(b"&lt;script&gt;", reader.data)
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO users VALUES ('other','Other',?,0,'now')",
                (self.password_hash,),
            )
        self.authenticate(self.client, "other")
        self.assertEqual(self.client.get("/materialy/" + mid).status_code, 404)
        self.assertEqual(self.client.get("/pliki/" + source).status_code, 404)

    def test_legacy_chapter_titles_describe_content(self):
        text = "## Część 1\n\nRola chlorofilu\nChlorofil pochłania światło.\n\n## Faza jasna\n\nEnergia światła jest przekształcana."
        chapters = note_chapters(text)
        self.assertEqual(
            [chapter["title"] for chapter in chapters],
            ["Rola chlorofilu", "Faza jasna"],
        )
        self.assertEqual(
            content_title("Fotosynteza dostarcza energii. Następne zdanie."),
            "Fotosynteza dostarcza energii",
        )
        self.assertEqual(
            note_chapters("Rola chlorofilu\n\nTreść notatki.")[0]["title"],
            "Rola chlorofilu",
        )

    def test_invalid_chapters_are_rejected_and_legacy_notes_keep_content(self):
        for chapters in [
            [],
            [{"title": "Rozdział", "content": ""}],
            [{"title": "Zły\ntytuł", "content": "Treść"}],
        ]:
            with self.assertRaises(ValueError):
                validate_draft({**draft(), "chapters": chapters})
        paragraphs = [str(i) + " " + "Treść notatki. " * 60 for i in range(8)]
        content = "\n\n".join(paragraphs)
        sections = note_chapters(content)
        self.assertGreater(len(sections), 1)
        self.assertEqual(
            "\n\n".join(section["content"] for section in sections), content.strip()
        )

    def test_ai_quiz_preview_and_save(self):
        uid = self.source()
        with self.app.app_context(), transaction() as db:
            db.execute(
                "UPDATE uploads SET draft_json=? WHERE id=?",
                (json.dumps(validate_draft(draft())), uid),
            )
        page = self.client.get("/pliki/" + uid)
        self.assertIn('aria-label="Warianty odpowiedzi"'.encode(), page.data)
        response = self.post(
            "/pliki/" + uid,
            {
                "title": "Fotosynteza",
                "guide": "Notatka AI",
                "selected": ["1"],
                "prompt_1": "Co dostarcza energii?",
                "answer_1": "Światło",
                "options_1": "Światło\nDźwięk\nGrawitacja",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            row = get_db().execute("SELECT * FROM activities").fetchone()
            self.assertEqual(row["kind"], "quiz")
            self.assertEqual(json.loads(row["options_json"])[0], "Światło")
        exported = self.client.get("/konto/eksport").data
        self.assertNotIn(b"access_token", exported)

    def test_generation_owner_and_csrf(self):
        uid = self.source()
        self.assertEqual(
            self.client.post("/pliki/" + uid + "/generuj-ai").status_code, 400
        )
        with self.app.app_context():
            get_db().execute(
                "INSERT INTO users VALUES ('other','Other',?,0,'now')",
                (self.password_hash,),
            )
        self.authenticate(self.client, "other")
        self.assertEqual(
            self.post("/pliki/" + uid + "/generuj-ai", {}).status_code, 404
        )

    def test_auth_disabled_in_public_deployment(self):
        self.app.config["CHATGPT_LOCAL_AUTH"] = False
        self.assertEqual(self.post("/konto/ai/polacz", {}).status_code, 403)

    def test_generation_controller_success_and_redirect(self):
        uid = self.source()
        with self.app.app_context():
            self.connection()

        class ImmediateThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with (
            patch(
                "madra.ai.chatgpt.models",
                return_value=[{"id": "gpt-5.6-terra", "name": "GPT-5.6 Terra"}],
            ),
            patch(
                "madra.ai.generate", return_value=validate_draft(draft())
            ) as generator,
            patch("madra.ai.threading.Thread", ImmediateThread),
        ):
            response = self.post(
                "/pliki/" + uid + "/generuj-ai",
                {"model": "tampered-model", "goal": "Zrozumieć fotosyntezę"},
            )
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            original = (
                get_db()
                .execute("SELECT filename,file_blob FROM uploads WHERE id=?", (uid,))
                .fetchone()
            )
        self.assertEqual(
            generator.call_args.args[1:3], (original["filename"], original["file_blob"])
        )
        self.assertEqual(generator.call_args.args[3], "gpt-5.6-terra")
        self.assertIn("/ai/zadania/", response.location)
        result = self.client.get(response.location)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.location, "/pliki/" + uid)
        with self.app.app_context():
            row = (
                get_db()
                .execute("SELECT draft_json FROM uploads WHERE id=?", (uid,))
                .fetchone()
            )
            self.assertEqual(json.loads(row[0])["generator"], "ai")
            self.assertEqual(json.loads(row[0])["goal"], "Zrozumieć fotosyntezę")

    def test_unavailable_fixed_model_cannot_start_request(self):
        uid = self.source()
        with self.app.app_context():
            self.connection()
        with (
            patch(
                "madra.ai.chatgpt.models",
                return_value=[{"id": "available", "name": "Available"}],
            ),
            patch("madra.ai.generate") as generate_mock,
        ):
            self.post("/pliki/" + uid + "/generuj-ai", {"model": "made-up"})
            generate_mock.assert_not_called()
        self.assertEqual(self.count("ai_jobs"), 0)

    def test_settings_csp_allows_only_official_auth_redirect(self):
        page = self.client.get("/konto/ai")
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            "form-action 'self' https://auth.openai.com",
            page.headers["Content-Security-Policy"],
        )
        self.assertIn("Kontynuuj z ChatGPT".encode("utf-8"), page.data)
