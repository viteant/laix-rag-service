from datetime import datetime, timedelta

from app.pipeline.models import PipelinePhase, PipelineRun, PipelineRunStatus


PHASES = tuple(PipelinePhase)


def next_execution_after(completed_at: datetime) -> datetime:
    """Schedule the successor exactly 24 hours after a successful completion."""
    return completed_at + timedelta(days=1)


class PipelineOrchestrator:
    """State transitions for public-source pipeline runs.

    This module deliberately contains no scheduler or worker invocation. Those
    adapters will be added after the R2 and processing phases are implemented.
    """

    @staticmethod
    def start(run: PipelineRun, now: datetime | None = None) -> PipelineRun:
        if run.status not in {PipelineRunStatus.PENDING.value, PipelineRunStatus.PAUSED.value}:
            raise ValueError(f"Cannot start a run in status '{run.status}'")
        run.status = PipelineRunStatus.RUNNING.value
        run.paused_at = None
        run.started_at = run.started_at or now or datetime.utcnow()
        return run

    @staticmethod
    def pause(run: PipelineRun, now: datetime | None = None) -> PipelineRun:
        if run.status != PipelineRunStatus.RUNNING.value:
            raise ValueError("Only a running pipeline can be paused")
        run.status = PipelineRunStatus.PAUSED.value
        run.paused_at = now or datetime.utcnow()
        return run

    @staticmethod
    def cancel(run: PipelineRun, reason: str, now: datetime | None = None) -> PipelineRun:
        if run.status in {PipelineRunStatus.COMPLETED.value, PipelineRunStatus.CANCELLED.value}:
            raise ValueError(f"Cannot cancel a run in status '{run.status}'")
        run.status = PipelineRunStatus.CANCELLED.value
        run.cancellation_reason = reason
        run.completed_at = now or datetime.utcnow()
        run.next_run_at = None
        return run

    @staticmethod
    def advance_phase(run: PipelineRun) -> PipelineRun:
        if run.status != PipelineRunStatus.RUNNING.value:
            raise ValueError("Only a running pipeline can advance phases")
        current_index = PHASES.index(PipelinePhase(run.current_phase))
        if current_index >= len(PHASES) - 1:
            raise ValueError("The pipeline is already in its final phase")
        run.current_phase = PHASES[current_index + 1].value
        return run

    @staticmethod
    def complete(run: PipelineRun, now: datetime | None = None) -> PipelineRun:
        if run.status != PipelineRunStatus.RUNNING.value:
            raise ValueError("Only a running pipeline can complete")
        if run.current_phase != PipelinePhase.CLEANUP.value:
            raise ValueError("A pipeline can complete only after the cleanup phase")
        completed_at = now or datetime.utcnow()
        run.status = PipelineRunStatus.COMPLETED.value
        run.completed_at = completed_at
        run.next_run_at = next_execution_after(completed_at)
        return run

    @staticmethod
    def fail(run: PipelineRun, message: str) -> PipelineRun:
        if run.status in {PipelineRunStatus.COMPLETED.value, PipelineRunStatus.CANCELLED.value}:
            raise ValueError(f"Cannot fail a run in status '{run.status}'")
        run.status = PipelineRunStatus.FAILED.value
        run.error_message = message
        run.next_run_at = None
        return run
