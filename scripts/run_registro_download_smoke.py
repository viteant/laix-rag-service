"""Download a small, auditable Registro Oficial sample without later phases."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.pipeline.connectors.registro_oficial import RegistroOficialConnector
from app.pipeline.discovery import DiscoveryService
from app.pipeline.executor import PublicPipelineExecutor
from app.pipeline.models import PipelineRun, PipelineRunStatus
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.public_sources import ensure_public_sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-subtype", type=int, default=2)
    args = parser.parse_args()
    db = SessionLocal()
    try:
        active = db.query(PipelineRun).filter(PipelineRun.status.in_([
            PipelineRunStatus.PENDING.value, PipelineRunStatus.RUNNING.value, PipelineRunStatus.PAUSED.value,
        ])).first()
        if active:
            raise RuntimeError(f"An active pipeline already exists: {active.id}")
        run = PipelineRun(trigger="manual-smoke")
        db.add(run)
        db.commit()
        db.refresh(run)
        discovery = DiscoveryService(db)
        for source in ensure_public_sources(db):
            connector = RegistroOficialConnector(source.source_subtype, source.base_url)
            for candidate in connector.discover(max_assets=args.per_subtype):
                discovery.record(run, source, candidate)
            db.commit()
        PublicPipelineExecutor(db).execute_current_phase(run)
        downloaded = [item for item in run.run_assets if item.status == "downloaded"]
        notify_pipeline_event(run, "prueba de descarga completada", f"Descargados {len(downloaded)} PDFs; no se ejecutaron fases posteriores.")
        print(f"RUN_ID={run.id}")
        print(f"DOWNLOADED={len(downloaded)}")
        return 0 if len(downloaded) == args.per_subtype * 6 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
