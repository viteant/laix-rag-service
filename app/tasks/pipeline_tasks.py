from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.pipeline.models import PipelineRun, PipelineRunStatus
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.public_sources import discover_public_sources
from app.pipeline.executor import PublicPipelineExecutor


@celery_app.task(name="app.tasks.pipeline_tasks.discover_public_sources_task")
def discover_public_sources_task(run_id: str) -> dict:
    """Persistently discover public assets and honor administrator controls."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if not run:
            return {"status": "error", "message": "Pipeline run not found"}
        if run.status == PipelineRunStatus.PENDING.value:
            PipelineOrchestrator.start(run)
            db.commit()
        if run.status != PipelineRunStatus.RUNNING.value:
            return {"status": run.status, "run_id": run_id}

        def should_continue() -> bool:
            db.refresh(run)
            return run.status == PipelineRunStatus.RUNNING.value

        def on_progress(subtype: str, folders_processed: int) -> None:
            db.refresh(run)
            if run.status != PipelineRunStatus.RUNNING.value:
                return
            summary = dict(run.summary or {})
            summary["discovery"] = {"subtype": subtype, "folders_processed": folders_processed}
            run.summary = summary
            db.commit()

        counts = discover_public_sources(db, run, should_continue, on_progress)
        db.refresh(run)
        if run.status != PipelineRunStatus.RUNNING.value:
            notify_pipeline_event(run, "descubrimiento detenido", f"Estado administrativo: {run.status}")
            return {"status": run.status, "run_id": run_id, "new_assets_by_subtype": counts}

        summary = dict(run.summary or {})
        summary["discovery_completed"] = True
        summary["new_assets_by_subtype"] = counts
        run.summary = summary
        db.commit()
        notify_pipeline_event(run, "descubrimiento completado", str(counts))
        return {"status": "completed", "run_id": run_id, "new_assets_by_subtype": counts}
    except Exception as error:
        db.rollback()
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if run:
            PipelineOrchestrator.fail(run, str(error))
            db.commit()
            notify_pipeline_event(run, "descubrimiento fallido", str(error))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.pipeline_tasks.discover_and_execute_public_pipeline_task")
def discover_and_execute_public_pipeline_task(run_id: str) -> dict:
    """Manual first-run worker: discover once, then execute phases in background."""
    discovery = discover_public_sources_task(run_id)
    if discovery.get("status") != "completed":
        return discovery
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        executor = PublicPipelineExecutor(db)
        while run and run.status == PipelineRunStatus.RUNNING.value:
            executor.execute_current_phase(run)
            db.refresh(run)
        return {"status": run.status if run else "error", "run_id": run_id, "phase": run.current_phase if run else None}
    finally:
        db.close()
