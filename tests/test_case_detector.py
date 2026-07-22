import unittest
from app.processing.metadata_extractor import MetadataExtractor


class TestMetadataExtractor(unittest.TestCase):
    def test_extract_tributario(self):
        sample_text = (
            "CORTE NACIONAL DE JUSTICIA\n"
            "SALA ESPECIALIZADA DE LO CONTENCIOSO TRIBUTARIO\n"
            "RECURSO No. 319-2011\n"
            "Juez Ponente: Dr. José Suing Nagua\n"
            "Quito, 21 de diciembre de 2012\n"
            "VISTOS: El Director del Servicio de Rentas Internas (SRI)..."
        )

        meta = MetadataExtractor.extract_metadata_from_text(sample_text)
        self.assertEqual(meta.court, "Corte Nacional de Justicia")
        self.assertEqual(meta.judge_rapporteur, "Dr. José Suing Nagua")
        self.assertEqual(meta.city, "Quito")
        self.assertEqual(meta.legal_area, "Contencioso Tributario")

    def test_extract_laboral_and_asunto(self):
        sample_text = (
            "RESOLUCIÓN No.: 850-09\n"
            "JUICIO No.: 960-07\n"
            "SENTENCIA MATERIA: LABORAL\n"
            "ASUNTO: Despido Intempestivo\n"
            "ACTOR: ROGER\n"
            "VISTOS: En el juicio por despido intempestivo..."
        )

        meta = MetadataExtractor.extract_metadata_from_text(sample_text)
        self.assertEqual(meta.legal_area, "Laboral y Social")
        self.assertEqual(meta.asunto, "LABORAL")


if __name__ == "__main__":
    unittest.main()
