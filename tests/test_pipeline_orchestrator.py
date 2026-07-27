from datetime import datetime, timedelta

import pytest

from app.pipeline.models import PipelinePhase, PipelineRun, PipelineRunStatus
from app.pipeline.orchestrator import PipelineOrchestrator, next_execution_after


def test_successful_pipeline_schedules_the_next_run_24_hours_later():
    completed_at = datetime(2026, 7, 27, 22, 0, 0)
    run = PipelineRun(status=PipelineRunStatus.RUNNING.value, current_phase=PipelinePhase.CLEANUP.value)

    PipelineOrchestrator.complete(run, completed_at)

    assert run.status == PipelineRunStatus.COMPLETED.value
    assert run.next_run_at == completed_at + timedelta(days=1)


@pytest.mark.parametrize("status", [PipelineRunStatus.FAILED.value, PipelineRunStatus.PAUSED.value, PipelineRunStatus.CANCELLED.value])
def test_non_successful_pipeline_does_not_schedule_a_successor(status):
    run = PipelineRun(status=PipelineRunStatus.RUNNING.value)

    if status == PipelineRunStatus.FAILED.value:
        PipelineOrchestrator.fail(run, "network error")
    elif status == PipelineRunStatus.PAUSED.value:
        PipelineOrchestrator.pause(run)
    else:
        PipelineOrchestrator.cancel(run, "administrator request")

    assert run.status == status
    assert run.next_run_at is None


def test_pipeline_cannot_complete_before_cleanup():
    run = PipelineRun(status=PipelineRunStatus.RUNNING.value, current_phase=PipelinePhase.INGEST_RAG.value)

    with pytest.raises(ValueError, match="cleanup"):
        PipelineOrchestrator.complete(run)
