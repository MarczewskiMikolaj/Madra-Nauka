import unittest
from html.parser import HTMLParser

from madra.services.formatting import render_content, render_note_content


class SolutionParts(HTMLParser):
    def __init__(self, value):
        super().__init__()
        self.hidden, self.visible, self.in_solution, self.panels = [], [], False, []
        self.feed(str(value))

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.in_solution = True
            self.panels.append(dict(attrs))

    def handle_endtag(self, tag):
        if tag == "details":
            self.in_solution = False

    def handle_data(self, data):
        (self.hidden if self.in_solution else self.visible).append(data)


class NoteSolutionTests(unittest.TestCase):
    def test_legacy_solution_collapses_without_hiding_next_task(self):
        html = render_note_content(
            "**Ćwiczenie praktyczne:** Policz.\n\n**Rozwiązanie:** 42.\n\nWyjaśnienie wyniku.\n\n**Kryterium przejścia:** Rozumiesz.\n\n**Ćwiczenie praktyczne:** Kolejne.\n\n**Rozwiązanie:** 7."
        )
        parts = SolutionParts(html)
        self.assertEqual(len(parts.panels), 2)
        self.assertTrue(all("open" not in attrs for attrs in parts.panels))
        self.assertIn("42.", "".join(parts.hidden))
        self.assertIn("Wyjaśnienie wyniku.", "".join(parts.hidden))
        self.assertIn("Kryterium przejścia:", "".join(parts.visible))
        self.assertIn("Kolejne.", "".join(parts.visible))
        self.assertNotIn("42.", "".join(parts.visible))

    def test_heading_solution_keeps_code_result_and_explanation_together(self):
        html = render_note_content(
            "### Ćwiczenie praktyczne\n\nPolicz.\n\n### Rozwiązanie\n\n```sql\nSELECT 42;\n```\n\nWynik: 42.\n\n#### Dlaczego\n\nUzasadnienie.\n\n### Dalej\n\nNowa teoria."
        )
        parts = SolutionParts(html)
        self.assertEqual(len(parts.panels), 1)
        self.assertIn("SELECT 42;", "".join(parts.hidden))
        self.assertIn("Uzasadnienie.", "".join(parts.hidden))
        self.assertIn("Nowa teoria.", "".join(parts.visible))

    def test_ordinary_worked_example_and_code_are_not_collapsed(self):
        text = "**Rozwiązany przykład:** Opis mechanizmu.\n\n```md\n### Rozwiązanie\n\n**Rozwiązanie:** przykład składni\n```"
        self.assertEqual(render_note_content(text), render_content(text))

    def test_raw_html_is_escaped_in_solution_and_unsafe_links_stay_disabled(self):
        html = str(
            render_note_content(
                "**Rozwiązanie:** <script>alert(1)</script>\n\n[klik](javascript:alert(1))\n\n<img src=x onerror=alert(1)>"
            )
        )
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img ", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("&lt;script&gt;", html)
        self.assertEqual(html.count("<details "), 1)

    def test_translated_solution_labels_are_collapsed(self):
        for label in (
            "Solution",
            "Answer",
            "Lösung",
            "Antwort",
            "Solución",
            "Respuesta",
        ):
            with self.subTest(label=label):
                parts = SolutionParts(
                    render_note_content("### " + label + "\n\nUkryty wynik.")
                )
                self.assertEqual(len(parts.panels), 1)
                self.assertNotIn("Ukryty wynik.", "".join(parts.visible))
