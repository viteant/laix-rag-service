"""Destructive bootstrap for the approved clean-slate deployment; never runs automatically."""
import argparse
import pathlib
import sys

from sqlalchemy import text

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.database import Base, engine
import app.database.models  # Register legacy RAG models.
import app.pipeline.models  # Register public-pipeline models.


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-reset", action="store_true", help="Required acknowledgement for dropping all tables")
    args = parser.parse_args()
    if not args.confirm_reset:
        parser.error("Refusing destructive reset without --confirm-reset")
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.commit()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Database reset completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
