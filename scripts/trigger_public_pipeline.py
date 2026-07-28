"""Entry point for the VPS timer: create a due successor, never a fixed-time run."""
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.core.config import settings
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.scheduler import create_due_successor
from app.tasks.pipeline_tasks import discover_public_sources_task


def main() -> int:
    while True:
        if settings.PUBLIC_PIPELINE_SCHEDULER_ENABLED:
            db = SessionLocal()
            try:
                run = create_due_successor(db)
                if run:
                    notify_pipeline_event(run, "programado", f"Creado {settings.PUBLIC_PIPELINE_INTERVAL_DAYS} días después de la finalización exitosa anterior.")
                    discover_public_sources_task.delay(str(run.id))
                    print(f"Scheduled public pipeline run: {run.id}")
            finally:
                db.close()
        time.sleep(60)


if __name__ == "__main__":
    raise SystemExit(main())
