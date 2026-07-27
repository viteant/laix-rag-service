from app.pipeline.connectors.registro_oficial import parse_edition_reference, parse_spanish_date, registro_oficial_asset


def test_registro_oficial_filename_follows_the_product_format():
    asset = registro_oficial_asset(
        title="Año I - Nº 203",
        publication_date="viernes, 30 enero 2026",
        subtype="registro_oficial",
        source_url="https://example.test/203.pdf",
    )

    assert asset.canonical_filename == "30012026_registro_oficial_A01203.pdf"
    assert asset.logical_identity == "registro_oficial:2026-01-30:A01:203"


def test_registro_oficial_date_and_edition_parsers_support_accents_and_roman_numerals():
    assert parse_spanish_date("Miércoles, 14 de enero de 2026").isoformat() == "2026-01-14"
    assert parse_edition_reference("Año IV - Nro. 8") == (4, 8)
