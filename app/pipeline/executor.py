from pathlib import Path

from sqlalchemy.orm import Session

from app.pipeline.downloader import DownloadService
from app.pipeline.models import PipelineAssetStatus, PipelinePhase, PipelineRun, PipelineRunAsset, PipelineRunStatus
from app.pipeline.orchestrator import PipelineOrchestrator
from app.pipeline.r2_storage import R2StorageService
from app.pipeline.rag_loader import RagTxtLoader
from app.pipeline.registro_classifier import RegistroOficialClassifier
from app.pipeline.transform import TransformService


class BatchExecutionError(RuntimeError):
    pass


class PublicPipelineExecutor:
    """Executes one phase at a time and enforces batch-wide phase barriers."""

    def __init__(self, db: Session, downloader=None, transformer=None, storage=None, rag_loader=None, classifier=None):
        self.db = db
        self.downloader = downloader or DownloadService(db)
        self.transformer = transformer or TransformService(db)
        self.storage = storage
        self.rag_loader = rag_loader or RagTxtLoader(db)
        self.classifier = classifier or RegistroOficialClassifier()

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
        failures = []
        for run_asset in self._run_assets(run):
            self._ensure_running(run)
            if run_asset.status == PipelineAssetStatus.SKIPPED.value:
                continue
            if run_asset.status != required_status:
                continue
            try:
                action(run_asset)
                self.db.commit()
            except Exception as error:
                self.db.rollback()
                run_asset.status = PipelineAssetStatus.FAILED.value
                run_asset.detail = str(error)
                run_asset.asset.status = PipelineAssetStatus.FAILED.value
                run_asset.asset.error_message = str(error)
                self.db.commit()
                failures.append(run_asset.asset.canonical_filename)
        if failures:
            PipelineOrchestrator.fail(run, f"Phase {run.current_phase} failed for: {', '.join(failures)}")
            self.db.commit()
            raise BatchExecutionError(run.error_message)

    def execute_current_phase(self, run: PipelineRun) -> PipelineRun:
        if run.status == PipelineRunStatus.PENDING.value:
            PipelineOrchestrator.start(run)
            self.db.commit()
        self._ensure_running(run)

        phase_actions = {
            PipelinePhase.DOWNLOAD.value: (PipelineAssetStatus.DISCOVERED.value, self.downloader.download),
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
        for value in {asset.downloaded_pdf_path, asset.optimized_pdf_path}:
            if value:
                Path(value).unlink(missing_ok=True)
        asset.status = PipelineAssetStatus.CLEANED.value
        run_asset.status = PipelineAssetStatus.CLEANED.value
