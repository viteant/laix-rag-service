import unittest
from app.processing.text_cleaner import TextCleaner


class TestTextCleaner(unittest.TestCase):
    def test_clean_text_basic(self):
        raw = "CORTE   NACIONAL   DE JUSTICIA\n\n\nJuicio  No. 114-2003\n\n"
        cleaned = TextCleaner.clean_text(raw)
        self.assertIn("CORTE NACIONAL DE JUSTICIA", cleaned)
        self.assertIn("Juicio No. 114-2003", cleaned)

    def test_hyphenated_word_join(self):
        raw = "El recurso de casacio-\nnal fue presentado por el actor."
        cleaned = TextCleaner.clean_text(raw)
        self.assertIn("casacional fue", cleaned)

    def test_control_characters(self):
        raw = "Texto con car\x00ácter nulo\x07."
        cleaned = TextCleaner.clean_text(raw)
        self.assertEqual(cleaned, "Texto con carácter nulo.")


if __name__ == "__main__":
    unittest.main()
