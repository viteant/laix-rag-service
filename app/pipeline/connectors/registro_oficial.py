import re
import unicodedata
from datetime import date

from app.pipeline.connectors.base import DiscoveredAsset


SPANISH_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


REGISTRO_OFICIAL_SUBTYPES = {
    "registro_oficial",
    "suplementos",
    "edicion_especial",
    "edicion_constitucional",
    "edicion_juridica",
    "indice_mensual",
}


def _normalized(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()


def parse_spanish_date(value: str) -> date:
    normalized = _normalized(value)
    match = re.search(r"(\d{1,2})\D+([a-z]+)\D+(\d{4})", normalized)
    if not match:
        raise ValueError(f"Unsupported Registro Oficial date: {value!r}")
    day, month_name, year = match.groups()
    month = SPANISH_MONTHS.get(month_name)
    if not month:
        raise ValueError(f"Unsupported Spanish month: {month_name!r}")
    return date(int(year), month, int(day))


def parse_edition_reference(title: str) -> tuple[int, int]:
    """Return edition year and issue number from strings such as 'Año I - Nº 203'."""
    normalized = _normalized(title)
    year_match = re.search(r"ano\s+([ivxlcdm]+|\d+)", normalized)
    issue_match = re.search(r"(?:n(?:o|ro|um)?|numero)\D*(\d+)", normalized)
    if not year_match or not issue_match:
        raise ValueError(f"Unsupported Registro Oficial title: {title!r}")

    raw_year = year_match.group(1)
    roman_values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    if raw_year.isdigit():
        edition_year = int(raw_year)
    else:
        edition_year = 0
        previous = 0
        for character in reversed(raw_year):
            value = roman_values[character]
            edition_year += -value if value < previous else value
            previous = max(previous, value)
    return edition_year, int(issue_match.group(1))


def registro_oficial_filename(publication_date: date, subtype: str, edition_year: int, issue_number: int) -> str:
    if subtype not in REGISTRO_OFICIAL_SUBTYPES:
        raise ValueError(f"Unsupported Registro Oficial subtype: {subtype!r}")
    # Año I, No. 203 becomes A01203, as specified by the product contract.
    edition_reference = f"A{edition_year:02d}{issue_number:03d}"
    return f"{publication_date:%d%m%Y}_{subtype}_{edition_reference}.pdf"


def registro_oficial_asset(title: str, publication_date: str, subtype: str, source_url: str) -> DiscoveredAsset:
    parsed_date = parse_spanish_date(publication_date)
    edition_year, issue_number = parse_edition_reference(title)
    filename = registro_oficial_filename(parsed_date, subtype, edition_year, issue_number)
    logical_identity = f"{subtype}:{parsed_date.isoformat()}:A{edition_year:02d}:{issue_number}"
    return DiscoveredAsset(
        logical_identity=logical_identity,
        canonical_filename=filename,
        source_url=source_url,
        metadata={
            "publication_date": parsed_date.isoformat(),
            "edition_year": str(edition_year),
            "issue_number": str(issue_number),
            "source_subtype": subtype,
            "display_title": title,
        },
    )
