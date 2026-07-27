from datetime import date


SPANISH_MONTHS = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")


def asset_log_context(run_asset) -> str:
    asset = run_asset.asset
    source = asset.source
    metadata = asset.metadata_json or {}
    publication_date = metadata.get("publication_date", "")
    year, month = "sin año", "sin mes"
    try:
        parsed = date.fromisoformat(publication_date)
        year, month = str(parsed.year), SPANISH_MONTHS[parsed.month - 1]
    except ValueError:
        pass
    return f"[{source.source_type} - {year} - {month} - {asset.canonical_filename}]"
