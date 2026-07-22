import sys
import pathlib
from datetime import datetime
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.core.config import settings
from app.database.models import LegalChunk
from app.retrieval.embedding_service import EmbeddingService

Base.metadata.create_all(bind=engine)


def embed_unprocessed_chunks(batch_size: int = 50):
    db: Session = SessionLocal()
    chunks = db.query(LegalChunk).filter(LegalChunk.embedding.is_(None)).all()

    if not chunks:
        print("ℹ️ Todos los chunks ya cuentan con embeddings vectoriales.")
        db.close()
        return

    print(f"🔮 Generando embeddings para {len(chunks)} chunks en PostgreSQL...\n")
    embedder = EmbeddingService()

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.content for c in batch]

        vectors = embedder.embed_documents(texts)

        for chunk_obj, vec in zip(batch, vectors):
            chunk_obj.embedding = vec
            chunk_obj.embedding_model = settings.EMBEDDING_MODEL
            chunk_obj.embedding_version = "1.0"
            chunk_obj.embedded_at = datetime.utcnow()

        db.commit()
        print(f"  ✅ Procesado lote de {len(batch)} chunks ({i + len(batch)}/{len(chunks)})")

    db.close()
    print("\n🎉 Generación de embeddings completada.")


if __name__ == "__main__":
    embed_unprocessed_chunks()
