from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_system
from app.pipeline.executor import PublicPipelineExecutor
from app.pipeline.models import PipelineRun, PipelineRunStatus
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.orchestrator import PipelineOrchestrator
from app.tasks.pipeline_tasks import discover_public_sources_task, execute_public_pipeline_task

router = APIRouter(prefix="/v1/admin/pipeline", tags=["Pipeline público"])


class CancelRequest(BaseModel):
    reason: str


def _run_or_404(db: Session, run_id: str) -> PipelineRun:
    run = db.query(PipelineRun).filter_by(id=run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


def _serialize(run: PipelineRun) -> dict:
    return {
        "id": str(run.id), "trigger": run.trigger, "status": run.status,
        "current_phase": run.current_phase, "requested_at": run.requested_at,
        "started_at": run.started_at, "completed_at": run.completed_at,
        "next_run_at": run.next_run_at, "error_message": run.error_message,
    }


@router.post("/runs", dependencies=[Depends(get_current_system)])
def create_manual_run(db: Session = Depends(get_db)):
    active = db.query(PipelineRun).filter(PipelineRun.status.in_([
        PipelineRunStatus.PENDING.value, PipelineRunStatus.RUNNING.value, PipelineRunStatus.PAUSED.value,
    ])).first()
    if active:
        raise HTTPException(status_code=409, detail=f"An active pipeline already exists: {active.id}")
    run = PipelineRun(trigger="manual")
    db.add(run)
    db.commit()
    db.refresh(run)
    notify_pipeline_event(run, "creado", "Lote manual listo para descubrimiento y descarga.")
    return _serialize(run)


@router.get("/runs", dependencies=[Depends(get_current_system)])
def list_runs(db: Session = Depends(get_db)):
    return [_serialize(run) for run in db.query(PipelineRun).order_by(PipelineRun.requested_at.desc()).limit(50)]


@router.post("/runs/{run_id}/discover", dependencies=[Depends(get_current_system)])
def discover_run_sources(run_id: str, db: Session = Depends(get_db)):
    run = _run_or_404(db, run_id)
    if run.status != PipelineRunStatus.PENDING.value:
        raise HTTPException(status_code=409, detail="Discovery requires a pending run")
    task = discover_public_sources_task.delay(str(run.id))
    return {"run": _serialize(run), "task_id": task.id}


@router.post("/runs/{run_id}/pause", dependencies=[Depends(get_current_system)])
def pause_run(run_id: str, db: Session = Depends(get_db)):
    run = _run_or_404(db, run_id)
    PipelineOrchestrator.pause(run)
    db.commit()
    notify_pipeline_event(run, "pausado", "Pausa solicitada por un administrador.")
    return _serialize(run)


@router.post("/runs/{run_id}/resume", dependencies=[Depends(get_current_system)])
def resume_run(run_id: str, db: Session = Depends(get_db)):
    run = _run_or_404(db, run_id)
    PipelineOrchestrator.start(run)
    db.commit()
    notify_pipeline_event(run, "reanudado", "Lote reanudado por un administrador.")
    if run.current_phase == "download" and not (run.summary or {}).get("discovery_completed"):
        task = discover_public_sources_task.delay(str(run.id))
        return {**_serialize(run), "task_id": task.id}
    task = execute_public_pipeline_task.delay(str(run.id))
    return {**_serialize(run), "task_id": task.id}


@router.post("/runs/{run_id}/cancel", dependencies=[Depends(get_current_system)])
def cancel_run(run_id: str, request: CancelRequest, db: Session = Depends(get_db)):
    run = _run_or_404(db, run_id)
    PipelineOrchestrator.cancel(run, request.reason)
    db.commit()
    notify_pipeline_event(run, "cancelado", request.reason)
    return _serialize(run)


@router.post("/runs/{run_id}/execute-phase", dependencies=[Depends(get_current_system)])
def execute_phase(run_id: str, db: Session = Depends(get_db)):
    run = _run_or_404(db, run_id)
    try:
        PublicPipelineExecutor(db).execute_current_phase(run)
    except Exception as error:
        notify_pipeline_event(run, "fallido", str(error))
        raise HTTPException(status_code=409, detail=str(error)) from error
    notify_pipeline_event(run, "fase completada", run.current_phase)
    return _serialize(run)
