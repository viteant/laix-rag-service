"""Entry point for the VPS timer: create a due successor, never a fixed-time run."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.scheduler import create_due_successor


def main() -> int:
    db = SessionLocal()
    try:
        run = create_due_successor(db)
        if not run:
            print("No public pipeline successor is due.")
            return 0
        notify_pipeline_event(run, "programado", "Creado 24 horas después de la finalización exitosa anterior.")
        print(f"Scheduled public pipeline run: {run.id}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
