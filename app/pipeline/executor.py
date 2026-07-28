from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.pipeline.downloader import DownloadService
from app.pipeline.models import PipelineAssetStatus, PipelinePhase, PipelineRun, PipelineRunAsset, PipelineRunStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.r2_storage import R2StorageService
from app.pipeline.rag_loader import RagTxtLoader
from app.pipeline.registro_classifier import RegistroOficialClassifier
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.storage_pressure import StoragePressureMonitor
from app.pipeline.logging_context import asset_log_context
from app.pipeline.transform import TransformService


class BatchExecutionError(RuntimeError):
    pass


class PublicPipelineExecutor:
    """Executes one phase at a time and enforces batch-wide phase barriers."""

    def __init__(self, db: Session, downloader=None, transformer=None, storage=None, rag_loader=None, classifier=None, space_monitor=None):
        self.db = db
        self.downloader = downloader or DownloadService(db)
        self.transformer = transformer or TransformService(db)
        self.storage = storage
        self.rag_loader = rag_loader or RagTxtLoader(db)
        self.classifier = classifier or RegistroOficialClassifier()
        self.space_monitor = space_monitor or StoragePressureMonitor()

    def _ensure_running(self, run: PipelineRun) -> None:
        self.db.refresh(run)
        if run.status == PipelineRunStatus.CANCELLED.value:
            raise BatchExecutionError("Pipeline was cancelled by an administrator")
        if run.status == PipelineRunStatus.PAUSED.value:
            raise BatchExecutionError("Pipeline was paused by an administrator")
        if run.status != PipelineRunStatus.RUNNING.value:
            raise BatchExecutionError(f"Pipeline is not running: {run.status}")

    def _run_assets(self, run: PipelineRun) -> list[PipelineRunAsset]:
        return self.db.query(PipelineRunAsset).filter_by(pipeline_run_id=run.id).order_by(PipelineRunAsset.created_at).all()

    def upload_and_verify(self, run_asset: PipelineRunAsset) -> None:
        if self.storage is None:
            self.storage = R2StorageService(self.db)
        self.storage.upload_and_verify(run_asset)

    def _execute_phase(self, run: PipelineRun, required_status: str, action) -> None:
        asset_ids = [item.id for item in self._run_assets(run) if item.status == required_status]
        configured_workers = (
            settings.PIPELINE_OCR_CONCURRENCY
            if run.current_phase == PipelinePhase.EXTRACT_TEXT.value
            else settings.PIPELINE_PROCESS_CONCURRENCY
        )
        workers = min(max(1, configured_workers), len(asset_ids) or 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(self._execute_asset_phase, run.id, asset_id, required_status, run.current_phase) for asset_id in asset_ids]
            for future in futures:
                future.result()

    @staticmethod
    def _action_for_phase(executor, phase: str):
        return {
            PipelinePhase.OPTIMIZE.value: executor.transformer.optimize,
            PipelinePhase.EXTRACT_TEXT.value: executor.transformer.extract_text,
            PipelinePhase.CLASSIFY_REGISTRO_OFICIAL.value: executor.classifier.classify,
            PipelinePhase.UPLOAD.value: executor.upload_and_verify,
            PipelinePhase.INGEST_RAG.value: executor.rag_loader.load,
            PipelinePhase.CLEANUP.value: executor.cleanup_local_pdfs,
        }[phase]

    @classmethod
    def _execute_asset_phase(cls, run_id, asset_id, required_status: str, phase: str) -> None:
        db = SessionLocal()
        try:
            run = db.query(PipelineRun).filter_by(id=run_id).first()
            run_asset = db.query(PipelineRunAsset).filter_by(id=asset_id).first()
            executor = cls(db)
            if not run or not run_asset or run_asset.status != required_status:
                return
            executor._ensure_running(run)
            try:
                print(f"{executor._phase_label(phase)} {asset_log_context(run_asset)}")
                cls._action_for_phase(executor, phase)(run_asset)
                db.commit()
            except Exception as error:
                db.rollback()
                run_asset = db.query(PipelineRunAsset).filter_by(id=asset_id).first()
                run_asset.status = PipelineAssetStatus.SKIPPED.value
                run_asset.detail = str(error)
                run_asset.asset.status = PipelineAssetStatus.FAILED.value
                run_asset.asset.error_message = str(error)
                db.commit()
                print(f"Perdido {asset_log_context(run_asset)}: {error}")
        finally:
            db.close()

    @staticmethod
    def _phase_label(phase: str) -> str:
        return {
            "optimize": "Optimizando",
            "extract_text": "Extrayendo texto",
            "classify_registro_oficial": "Clasificando",
            "upload": "Subiendo a R2",
            "ingest_rag": "Cargando RAG",
            "cleanup": "Limpiando PDF local",
        }.get(phase, phase)

    def _record_storage_pressure(self, run: PipelineRun, active: bool, cleaned: int = 0) -> None:
        snapshot = self.space_monitor.snapshot()
        summary = dict(run.summary or {})
        summary["storage_pressure"] = {
            "active": active, "free_percent": round(snapshot.free_percent, 2),
            "free_bytes": snapshot.free_bytes, "cleaned_pdfs": cleaned,
        }
        run.summary = summary

    def _relieve_storage_pressure(self, run: PipelineRun) -> bool:
        """Free only verified PDFs; TXT stays local and RAG remains deferred."""
        cleaned = 0
        # Once pressure begins, keep freeing verified PDFs until the recovery
        # threshold is reached; stopping at 20.01% would pause unnecessarily.
        while not self.space_monitor.recovered():
            concurrency = max(1, settings.PIPELINE_PROCESS_CONCURRENCY)
            candidates = [item.id for item in self._run_assets(run) if item.status in {
                PipelineAssetStatus.DOWNLOADED.value, PipelineAssetStatus.OPTIMIZED.value,
                PipelineAssetStatus.TEXT_READY.value, PipelineAssetStatus.CLASSIFIED.value,
                PipelineAssetStatus.VERIFIED.value,
            }][:concurrency]
            if not candidates:
                break
            with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
                results = list(pool.map(lambda asset_id: self._relieve_one_asset(run.id, asset_id), candidates))
            cleaned += sum(results)
            progressed = any(results) or bool(candidates)
            if not progressed:
                break
        self._record_storage_pressure(run, not self.space_monitor.recovered(), cleaned)
        self.db.commit()
        return self.space_monitor.recovered()

    @classmethod
    def _relieve_one_asset(cls, run_id, asset_id) -> int:
        db = SessionLocal()
        try:
            run = db.query(PipelineRun).filter_by(id=run_id).first()
            run_asset = db.query(PipelineRunAsset).filter_by(id=asset_id).first()
            executor = cls(db)
            if not run or not run_asset:
                return 0
            executor._ensure_running(run)
            phases = {
                PipelineAssetStatus.DOWNLOADED.value: ("Optimizando", executor.transformer.optimize),
                PipelineAssetStatus.OPTIMIZED.value: ("Extrayendo texto", executor.transformer.extract_text),
                PipelineAssetStatus.TEXT_READY.value: ("Clasificando", executor.classifier.classify),
                PipelineAssetStatus.CLASSIFIED.value: ("Subiendo a R2", executor.upload_and_verify),
            }
            while run_asset.status in phases:
                label, action = phases[run_asset.status]
                print(f"{label} {asset_log_context(run_asset)} [emergencia de almacenamiento]")
                action(run_asset)
                db.commit()
                db.refresh(run_asset)
            if run_asset.status == PipelineAssetStatus.VERIFIED.value and not (run_asset.asset.metadata_json or {}).get("emergency_pdf_cleaned_at"):
                print(f"Limpiando PDF local {asset_log_context(run_asset)} [emergencia de almacenamiento]")
                executor.delete_local_pdfs(run_asset)
                run_asset.asset.metadata_json = {**(run_asset.asset.metadata_json or {}), "emergency_pdf_cleaned_at": datetime.now(timezone.utc).isoformat()}
                db.commit()
                return 1
            return 0
        finally:
            db.close()

    def _execute_download_phase(self, run: PipelineRun) -> bool:
        """Download until complete, or pause/relieve when the data pool is low."""
        while True:
            pending = next((item for item in self._run_assets(run) if item.status == PipelineAssetStatus.DISCOVERED.value), None)
            if pending is None:
                return True
            if self.space_monitor.under_pressure():
                self._record_storage_pressure(run, True)
                self.db.commit()
                notify_pipeline_event(run, "presión de almacenamiento", "Se pausaron descargas y se inició limpieza segura de PDFs verificados.")
                if not self._relieve_storage_pressure(run):
                    PipelineOrchestrator.pause(run)
                    self.db.commit()
                    notify_pipeline_event(run, "pausado por almacenamiento", "No hay PDFs verificados suficientes para recuperar espacio.")
                    return False
                notify_pipeline_event(run, "almacenamiento recuperado", "Se reanudan las descargas del lote.")
                continue
            try:
                print(f"Descargando {asset_log_context(pending)}")
                self.downloader.download(pending)
                self.db.commit()
            except Exception as error:
                self.db.rollback()
                pending.status = PipelineAssetStatus.SKIPPED.value
                pending.detail = str(error)
                pending.asset.status = PipelineAssetStatus.FAILED.value
                pending.asset.error_message = str(error)
                self.db.commit()
                print(f"Perdido {asset_log_context(pending)}: {error}")
                continue

    def execute_current_phase(self, run: PipelineRun) -> PipelineRun:
        if run.status == PipelineRunStatus.PENDING.value:
            PipelineOrchestrator.start(run)
            self.db.commit()
        self._ensure_running(run)

        phase_actions = {
            PipelinePhase.OPTIMIZE.value: (PipelineAssetStatus.DOWNLOADED.value, self.transformer.optimize),
            PipelinePhase.EXTRACT_TEXT.value: (PipelineAssetStatus.OPTIMIZED.value, self.transformer.extract_text),
            PipelinePhase.CLASSIFY_REGISTRO_OFICIAL.value: (PipelineAssetStatus.TEXT_READY.value, self.classifier.classify),
            PipelinePhase.UPLOAD.value: (PipelineAssetStatus.CLASSIFIED.value, self.upload_and_verify),
            PipelinePhase.INGEST_RAG.value: (PipelineAssetStatus.VERIFIED.value, self.rag_loader.load),
            PipelinePhase.CLEANUP.value: (PipelineAssetStatus.INGESTED.value, self.cleanup_local_pdfs),
        }
        if run.current_phase == PipelinePhase.VERIFY_UPLOAD.value:
            PipelineOrchestrator.advance_phase(run)
            self.db.commit()
            return run

        if run.current_phase == PipelinePhase.DOWNLOAD.value:
            if not self._execute_download_phase(run):
                return run
            PipelineOrchestrator.advance_phase(run)
            self.db.commit()
            return run

        required_status, action = phase_actions[run.current_phase]
        self._execute_phase(run, required_status, action)
        if run.current_phase == PipelinePhase.CLEANUP.value:
            PipelineOrchestrator.complete(run)
        else:
            PipelineOrchestrator.advance_phase(run)
        self.db.commit()
        return run

    def cleanup_local_pdfs(self, run_asset: PipelineRunAsset) -> None:
        asset = run_asset.asset
        if not asset.r2_verified_at or not asset.local_txt_path or not Path(asset.local_txt_path).is_file():
            raise BatchExecutionError("Cleanup requires verified R2 storage and a local TXT")
        self.delete_local_pdfs(run_asset)
        asset.status = PipelineAssetStatus.CLEANED.value
        run_asset.status = PipelineAssetStatus.CLEANED.value

    @staticmethod
    def delete_local_pdfs(run_asset: PipelineRunAsset) -> None:
        for value in {run_asset.asset.downloaded_pdf_path, run_asset.asset.optimized_pdf_path}:
            if value:
                Path(value).unlink(missing_ok=True)
