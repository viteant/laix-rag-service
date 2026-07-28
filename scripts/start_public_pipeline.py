"""Manually create and enqueue one complete public-source pipeline batch."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.pipeline.manual_sources import register_manual_sources
from app.pipeline.models import PipelineRun, PipelineRunStatus
from app.tasks.pipeline_tasks import discover_and_execute_public_pipeline_task


def main() -> int:
    db = SessionLocal()
    try:
        active = db.query(PipelineRun).filter(PipelineRun.status.in_(["pending", "running", "paused"])).first()
        if active:
            raise RuntimeError(f"An active pipeline already exists: {active.id}")
        run = PipelineRun(trigger="manual")
        db.add(run); db.commit(); db.refresh(run)
        manual_assets = register_manual_sources(db, run)
        task = discover_and_execute_public_pipeline_task.delay(str(run.id))
        print(f"RUN_ID={run.id}")
        print(f"TASK_ID={task.id}")
        print(f"MANUAL_ASSETS={manual_assets}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
