from sqlalchemy.orm import Session

from collections.abc import Callable

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


def discover_public_sources(
    db: Session,
    run: PipelineRun,
    should_continue: Callable[[], bool] | None = None,
    on_progress: Callable[[str, int], None] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    discovery = DiscoveryService(db)
    for source in ensure_public_sources(db):
        if should_continue and not should_continue():
            break
        if not source.is_enabled:
            continue
        connector = RegistroOficialConnector(source.source_subtype, source.base_url)
        count = 0
        try:
            for candidate in connector.discover(
                should_continue=should_continue,
                on_progress=(lambda folders, subtype=source.source_subtype: on_progress(subtype, folders)) if on_progress else None,
            ):
                _, created = discovery.record(run, source, candidate)
                count += int(created)
        except Exception as error:
            print(f"Fail [{source.source_subtype} - descubrimiento]: {error}")
        db.commit()
        counts[source.source_subtype] = count
    return counts
