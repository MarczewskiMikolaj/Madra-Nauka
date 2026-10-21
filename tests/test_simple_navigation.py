"""The consolidated screens preserve navigation, ownership and learning actions."""

import unittest
from html.parser import HTMLParser

import test_mvp as fixtures
from madra.db import transaction
from madra.services.learning import now_iso


class PageElements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class SimpleNavigationTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.MVPTests.setUpClass.__func__)
    setUp = fixtures.MVPTests.setUp
    tearDown = fixtures.MVPTests.tearDown
    authenticate = fixtures.MVPTests.authenticate
    post = fixtures.MVPTests.post
    activity = fixtures.MVPTests.activity

    def test_old_destinations_land_on_expanded_sections(self):
        for old, section in [("/cele", "goals"), ("/postepy?page=2", "history")]:
            response = self.client.get(old, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.history), 1)
            elements = PageElements(response.get_data(as_text=True)).elements
            self.assertTrue(
                any(
                    tag == "details" and attrs.get("id") == section and "open" in attrs
                    for tag, attrs in elements
                )
            )
            if section == "history":
                self.assertIn("page=2", response.history[0].location)
        self.assertEqual(self.client.get("/dzisiaj?page=0").status_code, 400)

    def test_library_links_directly_to_visible_topics(self):
        html = self.client.get("/biblioteka").get_data(as_text=True)
        self.assertIn(f'href="/tematy/{self.tid}"', html)
        self.assertNotIn(f'href="/przedmioty/{self.wid}"', html)
        response = self.client.get(f"/przedmioty/{self.wid}")
        self.assertEqual(response.location, f"/biblioteka#subject-{self.wid}")
        self.assertEqual(self.client.get("/przedmioty/foreign-id").status_code, 404)
        with self.app.app_context(), transaction() as db:
            db.execute(
                "INSERT INTO content_states (kind,content_id,user_id,status,updated_at) VALUES ('topic',?,?,'archived',?)",
                (self.tid, self.uid, now_iso()),
            )
        html = self.client.get("/biblioteka").get_data(as_text=True)
        self.assertNotIn(f'href="/tematy/{self.tid}"', html)

    def test_home_has_two_destinations_and_starts_with_selected_budget(self):
        self.activity()
        html = self.client.get("/dzisiaj").get_data(as_text=True)
        nav = html.split('<nav aria-label="Nawigacja główna">')[1].split("</nav>")[0]
        self.assertEqual(nav.count("<a "), 2)
        self.assertIn("Nauka", nav)
        self.assertIn("Materiały", nav)
        elements = PageElements(html).elements
        start_form = next(
            attrs
            for tag, attrs in elements
            if tag == "form" and attrs.get("class") == "quick-study"
        )
        response = self.post(start_form["action"], {"budget": "7"})
        self.assertEqual(response.status_code, 302)
        from madra.db import get_db

        with self.app.app_context():
            study = get_db().execute("SELECT * FROM study_sessions").fetchone()
            self.assertEqual(study["budget_minutes"], 7)
