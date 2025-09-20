import pandas as pd
from sqlalchemy import create_engine
import os

# --- IMPORTANT ---
# Get the Public connection string from the Railway Postgres "Connect" tab
# and set it as an environment variable before running this script.
# On Windows PowerShell:
#   $env:DATABASE_URL = "postgresql://user:pass@host:port/db"
DATABASE_URL = os.environ.get("DATABASE_URL")
EXCEL_FILE_PATH = r"data/Tracker 2025-26.xlsx"  # Adjust if needed


def migrate():
  if not DATABASE_URL:
    raise RuntimeError(
      "DATABASE_URL is not set. Set it to the Public connection string from Railway Postgres and re-run."
    )
  print("Connecting to the database...")
  engine = create_engine(DATABASE_URL)

  print(f"Reading Excel file from {EXCEL_FILE_PATH}...")
  xls = pd.ExcelFile(EXCEL_FILE_PATH)

  sheet_configs = {
    "ASSET": "asset_schools",
    "CARES": "cares_schools",
    "Mindspark-Math": "mindspark_math_schools",
    "Mindspark-Eng": "mindspark_english_schools",
    "Mindspark-Science": "mindspark_science_schools",
    "Unique Schools": "all_unique_schools",
    "Sheet1": "summary_data",
  }

  for sheet_name in xls.sheet_names:
    if sheet_name in sheet_configs:
      table_name = sheet_configs[sheet_name]
      print(f"Processing sheet: '{sheet_name}' -> table: '{table_name}'")

      df = pd.read_excel(xls, sheet_name=sheet_name)

      # Clean up column names to be SQL-friendly
      df.columns = [
        str(col).strip().replace(" ", "_").replace("-", "_").lower()
        for col in df.columns
      ]

      # Add an 'id' column to be the primary key, if it doesn't exist
      if "id" not in df.columns:
        df.insert(0, "id", range(1, 1 + len(df)))

      # Use pandas to_sql to create table and insert data
      df.to_sql(table_name, engine, if_exists="replace", index=False)
      print(f"Successfully migrated {len(df)} rows to '{table_name}'.")


if __name__ == "__main__":
  migrate()
