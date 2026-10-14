"""PWA metadata and install icons must use the current application branding."""

import struct
import tempfile
import unittest
from pathlib import Path

from madra import create_app


class PWATests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": str(Path(self.directory.name) / "test.sqlite3"),
                "CLOUD_STATE_BUCKET": None,
            }
        )
        self.client = self.app.test_client()

    def test_manifest_and_install_icons_are_public_and_current(self):
        response = self.client.get("/manifest.json")
        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/manifest+json")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")
        manifest = response.get_json()
        # Match the legacy start URL so an existing installation retains its ID.
        self.assertEqual(manifest["id"], "/dashboard")
        self.assertNotEqual(self.client.get(manifest["start_url"]).status_code, 404)
        for icon in manifest["icons"]:
            with self.subTest(icon=icon["src"]):
                self.assertIn("mark-v2-", icon["src"])
                image = self.client.get(icon["src"])
                self.addCleanup(image.close)
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.mimetype, "image/png")
                self.assertEqual(image.data[:8], b"\x89PNG\r\n\x1a\n")
                dimensions = struct.unpack(">II", image.data[16:24])
                self.assertEqual("x".join(map(str, dimensions)), icon["sizes"])

    def test_public_pages_link_manifest_and_apple_icon(self):
        for path in ("/", "/login"):
            with self.subTest(path=path):
                html = self.client.get(path).get_data(as_text=True)
                self.assertIn('rel="manifest" href="/manifest.json"', html)
                self.assertIn('rel="apple-touch-icon"', html)
                self.assertIn("/static/icons/mark-v2-180.png", html)
        image = self.client.get("/static/icons/mark-v2-180.png")
        self.addCleanup(image.close)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(struct.unpack(">II", image.data[16:24]), (180, 180))
