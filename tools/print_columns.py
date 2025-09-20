import json
import sys
from pathlib import Path
from sqlalchemy import text

# Ensure project root is on sys.path so "import app" works
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import engine, SHEET_CONFIGS  # reuse app config/engine

def fetch_columns(conn, table_name: str):
    rs = conn.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
        """),
        {"schema": "public", "table": table_name}
    )
    return [r[0] for r in rs]

def main():
    out = {}
    with engine.connect() as conn:
        for table_name, cfg in SHEET_CONFIGS.items():
            cols = fetch_columns(conn, table_name)
            fixed_count = int(cfg.get('fixed_columns', 0))
            fixed_cols = cols[:fixed_count]
            editable_cols = [c for i, c in enumerate(cols) if (i + 1) > fixed_count and c != 'id']
            out[table_name] = {
                "name": cfg.get("name", table_name),
                "fixed_columns": fixed_count,
                "columns": cols,
                "fixed_cols": fixed_cols,
                "editable_cols": editable_cols,
            }
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()