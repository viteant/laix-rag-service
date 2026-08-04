from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from sqlalchemy import text
from app.pipeline.models import PipelineRun, PipelineRunStatus
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.public_sources import discover_public_sources, discover_public_source_subtype
from app.pipeline.connectors.registro_oficial import REGISTRO_OFICIAL_SECTIONS
from app.pipeline.executor import PublicPipelineExecutor
from app.pipeline.manual_sources import register_manual_sources


@celery_app.task(name="app.tasks.pipeline_tasks.process_scope_asset_task")
def process_scope_asset_task(run_id: str, asset_id: str) -> dict:
    """CPU-isolated document cycle used by the staged coordinator."""
    PublicPipelineExecutor._process_scope_asset(run_id, asset_id)
    return {"run_id": run_id, "asset_id": asset_id}


@celery_app.task(name="app.tasks.pipeline_tasks.ingest_verified_pipeline_assets_task")
def ingest_verified_pipeline_assets_task(run_id: str) -> dict:
    """Run partial RAG while download work is administratively paused."""
    db = SessionLocal()
    locked = False
    try:
        locked = bool(db.execute(text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": f"partial-rag:{run_id}"}).scalar())
        if not locked:
            return {"status": "already_running", "run_id": run_id}
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if not run:
            return {"status": "error", "message": "Pipeline run not found"}
        if run.status != PipelineRunStatus.PAUSED.value:
            return {"status": run.status, "message": "Partial RAG requires a paused pipeline", "run_id": run_id}
        notify_pipeline_event(run, "RAG parcial iniciado", "Se indexarán únicamente los activos verificados hasta este momento.")
        result = PublicPipelineExecutor(db).ingest_verified_assets_while_paused(run)
        notify_pipeline_event(run, "RAG parcial completado", f"Procesados: {result['processed']} · fallidos: {result['failed']}")
        return {"status": result["status"], "run_id": run_id, **result}
    except Exception as error:
        db.rollback()
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if run:
            summary = dict(run.summary or {})
            partial = dict(summary.get("partial_rag", {}))
            partial.update({"status": "failed", "error": str(error)})
            summary["partial_rag"] = partial
            run.summary = summary
            db.commit()
            notify_pipeline_event(run, "RAG parcial fallido", str(error))
        raise
    finally:
        if locked:
            db.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": f"partial-rag:{run_id}"})
        db.close()


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

        manual_assets = register_manual_sources(db, run)

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
        counts["manual"] = manual_assets
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
    return execute_staged_public_pipeline_task.run(run_id)


@celery_app.task(name="app.tasks.pipeline_tasks.execute_staged_public_pipeline_task")
def execute_staged_public_pipeline_task(run_id: str) -> dict:
    """Storage-first order: manual sources, then one Registro subtype at a time, RAG last."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if not run:
            return {"status": "error", "message": "Pipeline run not found"}
        if run.status == PipelineRunStatus.PENDING.value:
            PipelineOrchestrator.start(run)
            db.commit()
        executor = PublicPipelineExecutor(db)
        manual_assets = register_manual_sources(db, run)
        for source_type in ("jurisprudencia", "documentos"):
            executor._ensure_running(run)
            print(f"Procesando fuente manual [{source_type}] hasta R2")
            executor.process_scope_to_r2(run, source_type)

        for subtype in REGISTRO_OFICIAL_SECTIONS:
            executor._ensure_running(run)
            print(f"Descubriendo y procesando [registro_oficial - {subtype}]")
            discovered = discover_public_source_subtype(db, run, subtype)
            summary = dict(run.summary or {})
            summary["active_subtype"] = subtype
            summary.setdefault("staged_discovery", {})[subtype] = discovered
            run.summary = summary
            db.commit()
            run.current_phase = "download"
            if not executor._execute_download_phase(run, "registro_oficial", subtype):
                return {"status": run.status, "run_id": run_id, "phase": run.current_phase}
            executor.process_scope_to_r2(run, "registro_oficial", subtype)

        run.current_phase = "ingest_rag"
        db.commit()
        executor._execute_phase(run, PipelineAssetStatus.VERIFIED.value, executor.rag_loader.load)
        run.current_phase = "cleanup"
        executor._execute_phase(run, PipelineAssetStatus.INGESTED.value, executor.cleanup_local_pdfs)
        PipelineOrchestrator.complete(run)
        db.commit()
        return {"status": run.status, "run_id": run_id, "manual_assets": manual_assets}
    finally:
        db.close()


@celery_app.task(name="app.tasks.pipeline_tasks.execute_public_pipeline_task")
def execute_public_pipeline_task(run_id: str) -> dict:
    """Continue an already-discovered manual batch in the worker background."""
    db = SessionLocal()
    locked = False
    try:
        locked = bool(db.execute(text("SELECT pg_try_advisory_lock(hashtext(:run_id))"), {"run_id": run_id}).scalar())
        if not locked:
            return {"status": "already_running", "run_id": run_id}
        run = db.query(PipelineRun).filter_by(id=run_id).first()
        if run and run.current_phase == "download":
            register_manual_sources(db, run)
        executor = PublicPipelineExecutor(db)
        while run and run.status == PipelineRunStatus.RUNNING.value:
            executor.execute_current_phase(run)
            db.refresh(run)
        return {"status": run.status if run else "error", "run_id": run_id, "phase": run.current_phase if run else None}
    finally:
        if locked:
            db.execute(text("SELECT pg_advisory_unlock(hashtext(:run_id))"), {"run_id": run_id})
        db.close()
