"""Load Iceberg tables into DuckDB and build dbt gold marts."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import duckdb
from pyiceberg.catalog.sql import SqlCatalog

from gridpressure.config import DBT_DIR, DUCKDB_PATH


def _register(
    con: duckdb.DuckDBPyConnection, catalog: SqlCatalog, identifier: str, name: str
) -> int:
    table = catalog.load_table(identifier)
    frame = table.scan().to_arrow()
    con.register(f"_arrow_{name}", frame)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _arrow_{name}")
    con.unregister(f"_arrow_{name}")
    return frame.num_rows


def build_marts(catalog: SqlCatalog) -> dict[str, int]:
    if DUCKDB_PATH.exists():
        DUCKDB_PATH.unlink()
    con = duckdb.connect(str(DUCKDB_PATH))
    counts = {
        "silver_price": _register(con, catalog, "silver.price_interval", "silver_price"),
        "silver_scada": _register(con, catalog, "silver.unit_scada", "silver_scada"),
        "silver_duid": _register(con, catalog, "silver.duid", "silver_duid"),
        "silver_cpi": _register(con, catalog, "silver.cpi", "silver_cpi"),
        "silver_cash": _register(con, catalog, "silver.cash_rate", "silver_cash"),
    }
    con.close()
    dbt = Path(sys.executable).with_name("dbt")
    env = os.environ.copy()
    env["GRID_DUCKDB"] = str(DUCKDB_PATH)
    subprocess.run(
        [
            str(dbt),
            "build",
            "--project-dir",
            str(DBT_DIR),
            "--profiles-dir",
            str(DBT_DIR),
            "--no-use-colors",
        ],
        check=True,
        env=env,
    )
    return counts


def _iceberg_type(arrow_type):
    import pyarrow as pa
    from pyiceberg.types import (
        BooleanType,
        DateType,
        DoubleType,
        IntegerType,
        LongType,
        StringType,
        TimestampType,
    )

    if pa.types.is_string(arrow_type) or pa.types.is_large_string(arrow_type):
        return StringType()
    if pa.types.is_int32(arrow_type):
        return IntegerType()
    if pa.types.is_int64(arrow_type) or pa.types.is_uint64(arrow_type):
        return LongType()
    if pa.types.is_floating(arrow_type) or pa.types.is_decimal(arrow_type):
        return DoubleType()
    if pa.types.is_date(arrow_type):
        return DateType()
    if pa.types.is_timestamp(arrow_type):
        return TimestampType()
    if pa.types.is_boolean(arrow_type):
        return BooleanType()
    raise TypeError(f"Unsupported gold column type: {arrow_type}")


def export_gold_iceberg(catalog: SqlCatalog) -> list[str]:
    """Publish gold marts into Iceberg so Trino can query the same figures."""
    import pyarrow as pa
    from pyiceberg.schema import Schema
    from pyiceberg.types import NestedField

    from gridpressure.iceberg_store import ensure_table

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    written: list[str] = []
    try:
        for name in ("mart_region_month", "mart_fuel_day", "mart_cpi", "mart_cash"):
            frame = con.execute(f"SELECT * FROM {name}").to_arrow_table()
            columns = {}
            for field in frame.schema:
                column = frame.column(field.name)
                if pa.types.is_decimal(field.type):
                    column = column.cast(pa.float64())
                columns[field.name] = column
            frame = pa.table(columns)
            schema = Schema(
                *(
                    NestedField(index + 1, field.name, _iceberg_type(field.type), required=False)
                    for index, field in enumerate(frame.schema)
                )
            )
            identifier = f"gold.{name}"
            try:
                catalog.drop_table(identifier)
            except Exception:
                pass
            table = ensure_table(catalog, identifier, schema)
            if frame.num_rows:
                table.append(frame)
            written.append(identifier)
    finally:
        con.close()
    return written
