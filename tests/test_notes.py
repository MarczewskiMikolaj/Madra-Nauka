import unittest

from madra.services.notes import chapter_guide, note_chapters


class NoteChapterTests(unittest.TestCase):
    def test_learning_plan_and_chapters_share_one_order(self):
        chapters = [
            {"title": "Procesy", "content": "Procesy wykonują pracę."},
            {"title": "Pamięć", "content": "Pamięć przechowuje dane."},
        ]
        result = note_chapters(chapter_guide(chapters, [2, 1]))
        self.assertEqual([c["title"] for c in result], ["Pamięć", "Procesy"])

    def test_old_generated_plan_is_not_a_numbered_chapter(self):
        content = "## Plan nauki\n\nCzytaj rozdziały w tej kolejności:\n\n1. SGA\n\n## SGA\n\nWspólna pamięć."
        self.assertEqual(
            note_chapters(content), [{"title": "SGA", "content": "Wspólna pamięć."}]
        )

    def test_invalid_learning_orders_are_rejected(self):
        chapters = [{"title": "Temat", "content": "Wyjaśnienie."}]
        for order in [[], [1, 1], [2], [True], [1.0], "1"]:
            with self.subTest(order=order), self.assertRaises(ValueError):
                chapter_guide(chapters, order)

    def test_ai_subheadings_stay_inside_their_chapter(self):
        chapters = [
            {
                "title": "Mapa",
                "content": "## Kolejność\n\nPoznaj instancję.\n\n## Zakres\n\nRola DBA.",
            },
            {
                "title": "Instancja",
                "content": "# Definicja\n\nPamięć i procesy.\n\n## Przykład\n\nUruchomienie.",
            },
        ]
        result = note_chapters(chapter_guide(chapters))
        self.assertEqual([c["title"] for c in result], ["Mapa", "Instancja"])
        self.assertIn("### Kolejność", result[0]["content"])
        self.assertIn("#### Przykład", result[1]["content"])
        self.assertTrue(all(c["content"] for c in result))

    def test_existing_flattened_ai_note_has_no_empty_parent_cards(self):
        text = (
            "## Mapa\r\n\r\n## Kolejność nauki\r\n\r\nNajpierw instancja.\r\n"
            "\r\n## Rola DBA\r\n\r\nAdministracja.\r\n"
            "\r\n## SGA\r\n\r\n## Definicja\r\n\r\nWspólna pamięć."
        )
        result = note_chapters(text)
        self.assertEqual([c["title"] for c in result], ["Mapa", "SGA"])
        self.assertIn("Najpierw instancja.", result[0]["content"])
        self.assertIn("Administracja.", result[0]["content"])
        self.assertIn("Wspólna pamięć.", result[1]["content"])
        self.assertTrue(all(c["content"] for c in result))

    def test_nested_headings_and_fenced_code_do_not_split_chapters(self):
        text = "## Pierwszy\n\n### Sekcja\n\nTreść.\n\n```md\n## Przykład kodu\n```\n\n## Drugi\n\nKoniec."
        result = note_chapters(text)
        self.assertEqual([c["title"] for c in result], ["Pierwszy", "Drugi"])
        self.assertIn("## Przykład kodu", result[0]["content"])

    def test_serialization_preserves_heading_examples_in_code(self):
        body = "## Śródtytuł\n\n```md\n# Przykład\n```"
        guide = chapter_guide([{"title": "Rozdział", "content": body}])
        self.assertIn("### Śródtytuł", guide)
        self.assertIn("```md\n# Przykład\n```", guide)
        self.assertEqual(len(note_chapters(guide)), 1)

    def test_normal_flat_notes_keep_order(self):
        text = "## A\n\nTreść A.\n\n## B\n\nTreść B."
        self.assertEqual(
            note_chapters(text),
            [
                {"title": "A", "content": "Treść A."},
                {"title": "B", "content": "Treść B."},
            ],
        )
