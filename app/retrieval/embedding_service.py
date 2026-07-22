import math
import random
from typing import List
from app.core.config import settings


class EmbeddingService:
    _model_instance = None
    _engine_type = None

    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.EMBEDDING_MODEL
        self._load_model()

    def _load_model(self):
        if EmbeddingService._model_instance is not None:
            return

        # 1. Intentar cargar fastembed (ONNX runtime)
        try:
            from fastembed import TextEmbedding
            print(f"🧠 Cargando fastembed ONNX model...")
            EmbeddingService._model_instance = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            EmbeddingService._engine_type = "fastembed"
            print("✅ Modelo fastembed cargado exitosamente.")
            return
        except ImportError:
            pass

        # 2. Intentar cargar sentence-transformers
        try:
            from sentence_transformers import SentenceTransformer
            print(f"🧠 Cargando SentenceTransformer: {self.model_name}...")
            EmbeddingService._model_instance = SentenceTransformer(self.model_name)
            EmbeddingService._engine_type = "sentence_transformers"
            print("✅ Modelo SentenceTransformer cargado exitosamente.")
            return
        except ImportError:
            pass

        # 3. Fallback en Python puro si las librerías aún están instalándose
        print("⚠️ Usando generador vectorial ligero de desarrollo.")
        EmbeddingService._engine_type = "fallback"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        if EmbeddingService._engine_type == "fastembed":
            embeddings = list(EmbeddingService._model_instance.embed(texts))
            return [e.tolist() for e in embeddings]

        elif EmbeddingService._engine_type == "sentence_transformers":
            embeddings = EmbeddingService._model_instance.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            return embeddings.tolist()

        else:
            # Pseudo-random pseudo-semantic vector generator (768-dim, L2-normalized)
            results = []
            for text in texts:
                seed = abs(hash(text))
                rnd = random.Random(seed)
                raw_vec = [rnd.gauss(0, 1) for _ in range(768)]
                norm = math.sqrt(sum(x * x for x in raw_vec))
                norm_vec = [x / norm for x in raw_vec] if norm > 0 else raw_vec
                results.append(norm_vec)
            return results

    def embed_query(self, query: str) -> List[float]:
        if not query:
            return []
        res = self.embed_documents([query])
        return res[0] if res else []
