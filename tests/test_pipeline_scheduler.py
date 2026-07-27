from datetime import datetime, timedelta

from app.pipeline.orchestrator import next_execution_after


def test_next_scheduled_execution_is_relative_to_completion_not_calendar_time():
    completed = datetime(2026, 7, 27, 22, 0)
    assert next_execution_after(completed) == completed + timedelta(hours=24)
