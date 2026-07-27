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

# Cargar datos
status_df, type_df, recent_df, chunks_total, cases_total = get_metrics()

# Métricas Top
col1, col2, col3, col4 = st.columns(4)
total_docs = status_df["count"].sum() if not status_df.empty else 0
completed_docs = status_df[status_df["status"] == "completed"]["count"].sum() if not status_df.empty else 0

col1.metric("Total Documentos", int(total_docs))
col2.metric("Documentos Completados", int(completed_docs))
col3.metric("Casos Jurídicos Detectados", int(cases_total))
col4.metric("Chunks Generados (Vectores)", int(chunks_total))

st.markdown("---")

# Gráficos
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("Estado de Procesamiento")
    if not status_df.empty:
        fig_status = px.pie(status_df, values='count', names='status', color='status',
                            color_discrete_map={'completed':'green', 'processing':'orange', 'failed':'red', 'pending':'gray'})
        st.plotly_chart(fig_status, use_container_width=True)
    else:
        st.info("No hay datos suficientes para mostrar.")

with col_chart2:
    st.subheader("Tipos de Documentos")
    if not type_df.empty:
        fig_type = px.bar(type_df, x='source_type', y='count', color='source_type')
        st.plotly_chart(fig_type, use_container_width=True)
    else:
        st.info("No hay datos suficientes para mostrar.")

st.markdown("---")

# Tabla Reciente
st.subheader("Últimos Documentos Procesados")
if not recent_df.empty:
    st.dataframe(recent_df, use_container_width=True)
else:
    st.info("No se encontraron documentos en la base de datos.")

if st.button("🔄 Refrescar Datos"):
    st.cache_data.clear()
    st.rerun()
