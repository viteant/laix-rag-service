import time
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_db, Base, engine
from app.api.jurisprudence_router import router as jurisprudence_router
from app.api.admin_router import router as admin_router

# Intentar conectar a PostgreSQL con reintentos durante el arranque inicial
max_retries = 10
for i in range(max_retries):
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Tablas de la base de datos verificadas/creadas con éxito.")
        break
    except Exception as e:
        if i < max_retries - 1:
            print(f"⏳ Esperando a que PostgreSQL esté listo... (Intento {i+1}/{max_retries})")
            time.sleep(2)
        else:
            print(f"❌ Error conectando a PostgreSQL tras {max_retries} intentos: {e}")

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Servicio RAG Jurídico para LAIX Studio"
)

app.include_router(jurisprudence_router)
app.include_router(admin_router)


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    db_status = "ok"
    vector_enabled = False
    try:
        result = db.execute(text("SELECT 1")).scalar()
        if result != 1:
            db_status = "error"

        vector_res = db.execute(
            text("SELECT count(*) FROM pg_extension WHERE extname = 'vector';")
        ).scalar()
        vector_enabled = vector_res > 0
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "healthy" if db_status == "ok" else "unhealthy",
        "environment": settings.ENVIRONMENT,
        "database": db_status,
        "pgvector_extension": vector_enabled
    }
