from app.core.email import send_alert_email
from app.pipeline.models import PipelineRun


def notify_pipeline_event(run: PipelineRun, event: str, detail: str = "") -> bool:
    """Emit a distinct, debounced operational email for a pipeline transition."""
    subject = f"Pipeline {event}: {run.id}"
    body = (
        f"<h2>Pipeline público: {event}</h2>"
        f"<ul><li><b>Lote:</b> {run.id}</li>"
        f"<li><b>Estado:</b> {run.status}</li>"
        f"<li><b>Fase:</b> {run.current_phase}</li></ul>"
        f"<p>{detail}</p>"
    )
    return send_alert_email(subject, body, is_html=True)
