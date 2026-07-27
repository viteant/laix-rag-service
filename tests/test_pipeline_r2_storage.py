from types import SimpleNamespace

from app.pipeline.r2_storage import r2_key_for


def test_r2_key_is_grouped_by_type_subtype_and_publication_year():
    run_asset = SimpleNamespace(
        asset=SimpleNamespace(
            canonical_filename="30012026_registro_oficial_A01203.pdf",
            metadata_json={"publication_date": "2026-01-30"},
            source=SimpleNamespace(source_type="registro_oficial", source_subtype="registro_oficial"),
        )
    )

    assert r2_key_for(run_asset, "public") == "public/registro_oficial/registro_oficial/2026/30012026_registro_oficial_A01203.pdf"


def test_r2_key_preserves_manual_source_filename_without_date_folders():
    for source_type, original_filename in (
        ("jurisprudencia", "Sentencia No. 123-20-JP.pdf"),
        ("documentos", "Gaceta Judicial Extraordinaria.pdf"),
    ):
        run_asset = SimpleNamespace(
            asset=SimpleNamespace(
                canonical_filename=original_filename,
                metadata_json={},
                source=SimpleNamespace(source_type=source_type, source_subtype="default"),
            )
        )

        assert r2_key_for(run_asset, "public") == f"public/{source_type}/{original_filename}"
