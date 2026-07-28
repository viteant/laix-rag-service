from datetime import datetime

from sqlalchemy.orm import Session

from app.pipeline.models import PipelineRun, PipelineRunStatus


def create_due_successor(db: Session, now: datetime | None = None) -> PipelineRun | None:
    """Create one scheduled run after a successful predecessor reaches its interval."""
    now = now or datetime.utcnow()
    completed_runs = db.query(PipelineRun).filter(
        PipelineRun.status == PipelineRunStatus.COMPLETED.value,
        PipelineRun.next_run_at <= now,
    ).order_by(PipelineRun.next_run_at).all()
    for previous in completed_runs:
        exists = db.query(PipelineRun).filter_by(scheduled_from_run_id=previous.id).first()
        if not exists:
            run = PipelineRun(trigger="scheduled", scheduled_from_run_id=previous.id)
            db.add(run)
            db.commit()
            db.refresh(run)
            return run
    return None
