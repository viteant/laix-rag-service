from sqlalchemy.orm import Session

from app.pipeline.connectors.registro_oficial import REGISTRO_OFICIAL_SECTIONS, RegistroOficialConnector
from app.pipeline.discovery import DiscoveryService
from app.pipeline.models import PipelineRun, PipelineSource


def ensure_public_sources(db: Session) -> list[PipelineSource]:
    sources = []
    for subtype, url in REGISTRO_OFICIAL_SECTIONS.items():
        source = db.query(PipelineSource).filter_by(
            source_type="registro_oficial", source_subtype=subtype, connector_name="registro_oficial_playwright"
        ).first()
        if not source:
            source = PipelineSource(
                source_type="registro_oficial", source_subtype=subtype,
                connector_name="registro_oficial_playwright", base_url=url,
            )
            db.add(source)
        sources.append(source)
    db.commit()
    return sources


def discover_public_sources(db: Session, run: PipelineRun) -> dict[str, int]:
    counts: dict[str, int] = {}
    discovery = DiscoveryService(db)
    for source in ensure_public_sources(db):
        if not source.is_enabled:
            continue
        connector = RegistroOficialConnector(source.source_subtype, source.base_url)
        count = 0
        for candidate in connector.discover():
            _, created = discovery.record(run, source, candidate)
            count += int(created)
        db.commit()
        counts[source.source_subtype] = count
    return counts
