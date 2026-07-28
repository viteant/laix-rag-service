import os
import sys
import pathlib
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from dotenv import load_dotenv

# Asegurar que importamos los modulos correctamente
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
from app.core.database import SessionLocal
from app.core.config import settings
from app.pipeline.models import PipelineRun
from app.pipeline.notifier import notify_pipeline_event
from app.pipeline.orchestrator import PipelineOrchestrator
from app.tasks.pipeline_tasks import execute_staged_public_pipeline_task

load_dotenv()

# Configuración de página
st.set_page_config(page_title="LAIX RAG Dashboard", page_icon="⚖️", layout="wide")

# --- SISTEMA DE LOGIN SIMPLE ---
def check_password():
    """Returns `True` if the user had a correct password."""
    def password_entered():
        if (
            st.session_state["username"] == os.getenv("DASHBOARD_USER", "admin")
            and st.session_state["password"] == os.getenv("DASHBOARD_PASSWORD", "admin")
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.header("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        st.header("🔒 Acceso Restringido")
        st.text_input("Usuario", key="username")
        st.text_input("Contraseña", type="password", key="password")
        st.button("Ingresar", on_click=password_entered)
        st.error("😕 Usuario o contraseña incorrectos")
        return False
    else:
        return True

if not check_password():
    st.stop()  # Detiene la ejecución si no está autenticado

# --- DASHBOARD PRINCIPAL ---

st.title("📊 LAIX RAG - Dashboard de Ingesta")
st.markdown("Monitoreo en tiempo real de los documentos procesados por el motor de IA.")

# Funciones de carga de datos
@st.cache_data(ttl=30)
def get_metrics():
    db = SessionLocal()
    try:
        # Documentos procesados por estado
        status_query = "SELECT status, COUNT(*) as count FROM source_documents GROUP BY status"
        status_df = pd.read_sql_query(status_query, db.bind)

        # Documentos procesados por tipo
        type_query = "SELECT source_type, COUNT(*) as count FROM source_documents GROUP BY source_type"
        type_df = pd.read_sql_query(type_query, db.bind)

        # Últimos documentos ingresados
        recent_query = "SELECT filename, status, source_type, created_at FROM source_documents ORDER BY created_at DESC LIMIT 15"
        recent_df = pd.read_sql_query(recent_query, db.bind)

        # Total chunks
        chunks_query = "SELECT COUNT(*) as total_chunks FROM legal_chunks"
        chunks_total = db.execute(text(chunks_query)).scalar() or 0

        # Total casos
        cases_query = "SELECT COUNT(*) as total_cases FROM legal_cases"
        cases_total = db.execute(text(cases_query)).scalar() or 0

        return status_df, type_df, recent_df, chunks_total, cases_total
    finally:
        db.close()


@st.cache_data(ttl=10)
def get_pipeline_metrics():
    """Read batch assets directly so progress is visible before RAG ingestion."""
    db = SessionLocal()
    try:
        run = db.query(PipelineRun).filter(PipelineRun.status.in_(("running", "paused"))).order_by(PipelineRun.requested_at.desc()).first()
        if not run:
            run = db.query(PipelineRun).order_by(PipelineRun.requested_at.desc()).first()
        if not run:
            return None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        params = {"run_id": str(run.id)}
        status_df = pd.read_sql_query(text("""
            SELECT pra.status, COUNT(*) AS count
            FROM pipeline_run_assets pra
            WHERE pra.pipeline_run_id = :run_id
            GROUP BY pra.status ORDER BY pra.status
        """), db.bind, params=params)
        type_df = pd.read_sql_query(text("""
            SELECT ps.source_type, COUNT(*) AS count
            FROM pipeline_run_assets pra
            JOIN pipeline_assets pa ON pa.id = pra.asset_id
            JOIN pipeline_sources ps ON ps.id = pa.source_id
            WHERE pra.pipeline_run_id = :run_id
            GROUP BY ps.source_type ORDER BY ps.source_type
        """), db.bind, params=params)
        recent_df = pd.read_sql_query(text("""
            SELECT ps.source_type AS tipo, ps.source_subtype AS subtipo,
                   pa.canonical_filename AS archivo, pra.status AS estado,
                   pra.updated_at AS actualizado, pa.r2_verified_at AS r2_verificado,
                   pra.detail AS detalle
            FROM pipeline_run_assets pra
            JOIN pipeline_assets pa ON pa.id = pra.asset_id
            JOIN pipeline_sources ps ON ps.id = pa.source_id
            WHERE pra.pipeline_run_id = :run_id
            ORDER BY pra.updated_at DESC
            LIMIT 20
        """), db.bind, params=params)
        run_info = {
            "id": str(run.id), "estado": run.status, "fase": run.current_phase,
            "summary": run.summary or {},
        }
        return run_info, status_df, type_df, recent_df
    finally:
        db.close()

# Cargar datos
status_df, type_df, recent_df, chunks_total, cases_total = get_metrics()
pipeline_run, pipeline_status_df, pipeline_type_df, pipeline_recent_df = get_pipeline_metrics()
has_pipeline_assets = not pipeline_status_df.empty
display_status_df = pipeline_status_df if has_pipeline_assets else status_df
display_type_df = pipeline_type_df if has_pipeline_assets else type_df
display_recent_df = pipeline_recent_df if has_pipeline_assets else recent_df

pipeline_tab, rag_tab, resources_tab = st.tabs(["Pipeline", "RAG", "Recursos"])

with pipeline_tab:
    col1, col2 = st.columns(2)
    total_docs = display_status_df["count"].sum() if not display_status_df.empty else 0
    ready_statuses = {"completed", "verified", "ingested", "cleaned"}
    completed_docs = display_status_df[display_status_df["status"].isin(ready_statuses)]["count"].sum() if not display_status_df.empty else 0
    col1.metric("Activos del lote" if has_pipeline_assets else "Total Documentos", int(total_docs))
    col2.metric("Verificados / completados", int(completed_docs))
    if pipeline_run:
        st.caption(f"Lote mostrado: {pipeline_run['id']} · estado {pipeline_run['estado']} · fase {pipeline_run['fase']}")
        pressure = pipeline_run["summary"].get("storage_pressure", {})
        if pressure:
            free_percent = float(pressure.get("free_percent", 0))
            recovery_target = settings.PIPELINE_RESUME_FREE_SPACE_PERCENT
            space_col, progress_col = st.columns([1, 3])
            space_col.metric("Espacio libre del pool", f"{free_percent:.1f}%")
            progress_col.progress(min(free_percent / recovery_target, 1.0), text=f"Recuperación de disco: {free_percent:.1f}% / {recovery_target:.0f}% · PDFs liberados: {pressure.get('cleaned_pdfs', 0)}")

    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.subheader("Estado de Procesamiento")
        if not display_status_df.empty:
            fig_status = px.pie(display_status_df, values='count', names='status', color='status', color_discrete_map={'completed':'green', 'verified':'green', 'ingested':'green', 'cleaned':'green', 'classified':'blue', 'text_ready':'blue', 'optimized':'orange', 'downloaded':'orange', 'discovered':'gray', 'failed':'red', 'skipped':'red'})
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.info("No hay datos suficientes para mostrar.")
    with col_chart2:
        st.subheader("Tipos de Documentos")
        if not display_type_df.empty:
            st.plotly_chart(px.bar(display_type_df, x='source_type', y='count', color='source_type'), use_container_width=True)
        else:
            st.info("No hay datos suficientes para mostrar.")

    st.subheader("Últimos Activos del Pipeline" if has_pipeline_assets else "Últimos Documentos Procesados")
    if not display_recent_df.empty:
        st.dataframe(display_recent_df, use_container_width=True, hide_index=True)
    else:
        st.info("No se encontraron activos del pipeline ni documentos en la base de datos.")
    if st.button("🔄 Refrescar Datos"):
        st.cache_data.clear()
        st.rerun()

with rag_tab:
    rag_col1, rag_col2, rag_col3 = st.columns(3)
    rag_col1.metric("Documentos indexados", int(status_df["count"].sum()) if not status_df.empty else 0)
    rag_col2.metric("Casos jurídicos detectados", int(cases_total))
    rag_col3.metric("Chunks generados (vectores)", int(chunks_total))
    st.subheader("Estado del RAG")
    if not status_df.empty:
        st.plotly_chart(px.pie(status_df, values="count", names="status", color="status"), use_container_width=True)
    else:
        st.info("El RAG se ejecutará cuando todos los TXT del lote estén listos.")

with resources_tab:
    st.subheader("Recursos del worker")
    runtime = (pipeline_run or {}).get("summary", {}).get("runtime", {})
    if runtime:
        def gib(value):
            return f"{value / 1024 ** 3:.2f} GB" if value is not None else "Sin límite"
        memory = gib(runtime.get("memory_bytes"))
        limit = runtime.get("memory_limit_bytes")
        memory_label = f"{memory} / {gib(limit)}" if limit else memory
        resource_col1, resource_col2, resource_col3, resource_col4 = st.columns(4)
        resource_col1.metric("Memoria del worker", memory_label)
        resource_col2.metric("Swap del worker", gib(runtime.get("swap_bytes")))
        resource_col3.metric("Carga del servidor", f"{runtime.get('load_1', 0):.2f}", help="Promedio de carga del último minuto.")
        resource_col4.metric("Disco de datos libre", f"{runtime.get('data_free_percent', 0):.1f}%")
        st.caption(f"Última lectura: {runtime.get('recorded_at', 'sin datos')} · carga 5/15 min: {runtime.get('load_5', 0):.2f} / {runtime.get('load_15', 0):.2f}")
    else:
        st.info("Las métricas aparecerán al iniciar o reanudar un ciclo de documentos.")

@st.cache_data(ttl=15)
def get_pipeline_runs():
    db = SessionLocal()
    try:
        rows = db.query(PipelineRun).order_by(PipelineRun.requested_at.desc()).limit(20).all()
        return [{
            "id": str(row.id), "origen": row.trigger, "estado": row.status,
            "fase": row.current_phase, "solicitado": row.requested_at,
            "siguiente ejecución": row.next_run_at, "error": row.error_message,
        } for row in rows]
    finally:
        db.close()


with pipeline_tab:
    st.markdown("---")
    st.subheader("Pipeline de fuentes públicas")
    pipeline_runs = get_pipeline_runs()
    if pipeline_runs:
        st.dataframe(pd.DataFrame(pipeline_runs), use_container_width=True)
        db = SessionLocal()
        try:
            active_row = next((row for row in pipeline_runs if row["estado"] in {"running", "paused"}), None)
            if active_row:
                counts = db.execute(text("SELECT status, count(*) FROM pipeline_run_assets WHERE pipeline_run_id = :run_id GROUP BY status"), {"run_id": active_row["id"]}).all()
                st.caption("Progreso por estado: " + " · ".join(f"{status}: {count}" for status, count in counts))
        finally:
            db.close()
        active = next((run for run in pipeline_runs if run["estado"] in {"running", "paused"}), None)
        if active:
            st.caption(f"Lote activo: {active['id']} · fase {active['fase']}")
            action_col, reason_col = st.columns([1, 2])
            reason = reason_col.text_input("Motivo de cancelación", key="pipeline_cancel_reason")
            db = SessionLocal()
            try:
                run = db.query(PipelineRun).filter_by(id=active["id"]).first()
                if action_col.button("Pausar lote", disabled=active["estado"] != "running"):
                    PipelineOrchestrator.pause(run)
                    db.commit()
                    notify_pipeline_event(run, "pausado", "Pausa solicitada desde el dashboard.")
                    st.cache_data.clear()
                    st.rerun()
                if action_col.button("Reanudar lote", disabled=active["estado"] != "paused"):
                    PipelineOrchestrator.start(run)
                    db.commit()
                    notify_pipeline_event(run, "reanudado", "Reanudado desde el dashboard.")
                    execute_staged_public_pipeline_task.delay(str(run.id))
                    st.cache_data.clear()
                    st.rerun()
                if action_col.button("Cancelar lote", disabled=not reason):
                    PipelineOrchestrator.cancel(run, reason)
                    db.commit()
                    notify_pipeline_event(run, "cancelado", reason)
                    st.cache_data.clear()
                    st.rerun()
            finally:
                db.close()
    else:
        st.info("Aún no hay lotes públicos registrados.")
