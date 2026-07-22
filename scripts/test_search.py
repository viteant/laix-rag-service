import sys
import pathlib
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.retrieval.hybrid_search import HybridSearch
from app.database.models import LegalCase

Base.metadata.create_all(bind=engine)


def test_hybrid_queries():
    db: Session = SessionLocal()
    searcher = HybridSearch(db)

    test_queries = [
        ("¿Cuándo procede el recurso de revisión en materia tributaria?", {"legal_area": "Contencioso Tributario"}),
        ("Despido intempestivo y reliquidación de haberes", {"legal_area": "Laboral y Social"}),
        ("Recurso No. 319-2011", None),
        ("Corte Nacional de Justicia casación", None),
    ]

    print("🔎 Probando Búsqueda Híbrida (Vectorial + Full-Text FTS)...\n")

    for q_text, filters in test_queries:
        print("==================================================")
        print(f"❓ Consulta: '{q_text}'")
        if filters:
            print(f"   Filtros: {filters}")

        results = searcher.search(query=q_text, limit=3, filters=filters)
        print(f"   Resultados encontrados: {len(results)}\n")

        for r_idx, r in enumerate(results, 1):
            clean_fragment = r['content'][:140].replace("\n", " ")
            print(f"   🏆 #{r_idx} [Score: {r['score']} | Coincidencia: {r['match_type']}]")
            print(f"      - Juicio / Recurso: {r['case_number'] or 'N/A'}")
            print(f"      - Materia:          {r['legal_area']}")
            print(f"      - Tribunal:         {r['court'] or 'N/A'}")
            print(f"      - Páginas:          {r['page_start']}-{r['page_end']} (Sección: {r['section_type']})")
            print(f"      - Fragmento:        \"{clean_fragment}...\"\n")

    db.close()


if __name__ == "__main__":
    test_hybrid_queries()
