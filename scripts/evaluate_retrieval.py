import json
import sys
import pathlib
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import SessionLocal, engine, Base
from app.retrieval.hybrid_search import HybridSearch

Base.metadata.create_all(bind=engine)


def run_evaluation():
    db: Session = SessionLocal()
    searcher = HybridSearch(db)

    json_path = pathlib.Path(__file__).parent.parent / "tests" / "evaluation" / "questions.json"
    if not json_path.exists():
        print(f"❌ No se encontró el archivo de evaluación en {json_path}")
        db.close()
        return

    with open(json_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    print(f"📊 Ejecutando Evaluación de Recuperación sobre {len(questions)} preguntas...\n")

    hits_top1 = 0
    hits_top3 = 0
    hits_top5 = 0

    for q in questions:
        q_id = q["id"]
        q_text = q["question"]
        expected_case = q["expected_case_number"]

        results = searcher.search(query=q_text, limit=5)
        retrieved_cases = [r["case_number"] for r in results]

        hit1 = expected_case in retrieved_cases[:1]
        hit3 = expected_case in retrieved_cases[:3]
        hit5 = expected_case in retrieved_cases[:5]

        if hit1:
            hits_top1 += 1
        if hit3:
            hits_top3 += 1
        if hit5:
            hits_top5 += 1

        print(f"Pregunta [{q_id}]: '{q_text}'")
        print(f"  - Esperado: Juicio {expected_case}")
        print(f"  - Recuperados: {retrieved_cases}")
        print(f"  - Hit@1: {'✅' if hit1 else '❌'} | Hit@3: {'✅' if hit3 else '❌'} | Hit@5: {'✅' if hit5 else '❌'}\n")

    total = len(questions)
    p_top1 = (hits_top1 / total) * 100
    p_top3 = (hits_top3 / total) * 100
    p_top5 = (hits_top5 / total) * 100

    print("==================================================")
    print("📈 RESULTADOS DE LA EVALUACIÓN DE RECUPERACIÓN (RETRIEVAL):")
    print(f"  - Hit@1 Rate: {p_top1:.1f}% ({hits_top1}/{total})")
    print(f"  - Hit@3 Rate: {p_top3:.1f}% ({hits_top3}/{total})")
    print(f"  - Hit@5 Rate: {p_top5:.1f}% ({hits_top5}/{total})")
    print("==================================================")

    db.close()


if __name__ == "__main__":
    run_evaluation()
