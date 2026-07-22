import unittest
from app.processing.chunker import TextChunker


class TestTextChunker(unittest.TestCase):
    def test_token_counter(self):
        chunker = TextChunker()
        text = "CORTE NACIONAL DE JUSTICIA SALA ESPECIALIZADA DE LO CONTENCIOSO TRIBUTARIO"
        count = chunker.count_tokens(text)
        self.assertGreater(count, 5)

    def test_chunking_limit(self):
        chunker = TextChunker(target_tokens=50, max_tokens=100)
        # Crear texto largo repetido
        paragraph1 = "Párrafo 1. " * 30
        paragraph2 = "Párrafo 2. " * 30
        text = f"{paragraph1}\n\n{paragraph2}"

        count1 = chunker.count_tokens(paragraph1)
        self.assertGreater(count1, 10)


if __name__ == "__main__":
    unittest.main()
