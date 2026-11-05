"""Register local Iceberg tables in Trino and compare one aggregate with DuckDB."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
from trino.dbapi import connect

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "warehouse" / "iceberg_tables.json"
DUCK = ROOT / "data" / "warehouse" / "grid.duckdb"


def trino_rows(sql: str) -> list[tuple]:
    conn = connect(host="localhost", port=8080, user="grid", catalog="iceberg", schema="gold")
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def main() -> None:
    tables = json.loads(INDEX.read_text(encoding="utf-8"))
    conn = connect(host="localhost", port=8080, user="grid")
    cur = conn.cursor()
    for schema in ("bronze", "silver", "gold", "ops"):
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS iceberg.{schema}")
    for table in tables:
        location = table["location"]
        statement = (
            "CALL iceberg.system.register_table("
            f"schema_name => '{table['schema']}', "
            f"table_name => '{table['table']}', "
            f"table_location => '{location}')"
        )
        try:
            cur.execute(statement)
            print("registered", table["schema"], table["table"])
        except Exception as exc:  # table may already be registered
            print("skip", table["schema"], table["table"], exc)
    cur.close()
    conn.close()
    sql = (
        "SELECT region, round(avg(demand_weighted_rrp), 2) "
        "FROM iceberg.gold.mart_region_month GROUP BY 1 ORDER BY 1"
    )
    trino_result = trino_rows(sql)
    duck = duckdb.connect(str(DUCK), read_only=True)
    duck_result = duck.execute(
        """
        SELECT region, round(avg(demand_weighted_rrp), 2)
        FROM mart_region_month
        GROUP BY 1
        ORDER BY 1
        """
    ).fetchall()
    duck.close()
    print("trino", trino_result)
    print("duckdb", duck_result)
    if trino_result != [tuple(row) for row in duck_result]:
        raise SystemExit("Trino and DuckDB gold averages differ")
    print("Trino and DuckDB agree")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise
