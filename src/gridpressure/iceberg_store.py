"""Local PyIceberg catalog and bronze/silver tables."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    DateType,
    DoubleType,
    IntegerType,
    NestedField,
    StringType,
    TimestampType,
)

from gridpressure.config import CATALOG_DB, ICEBERG_DIR, WAREHOUSE
from gridpressure.mor import merge_on_read_replace, snapshot_delete_counts

_PROPERTIES = {
    "write.delete.mode": "merge-on-read",
    "write.update.mode": "merge-on-read",
    "write.merge.mode": "merge-on-read",
    "format-version": "2",
}


def open_catalog() -> SqlCatalog:
    WAREHOUSE.mkdir(parents=True, exist_ok=True)
    ICEBERG_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_DB.parent.mkdir(parents=True, exist_ok=True)
    catalog = SqlCatalog(
        "grid",
        **{"uri": f"sqlite:///{CATALOG_DB}", "warehouse": str(ICEBERG_DIR)},
    )
    for name in ("bronze", "silver", "gold", "ops"):
        try:
            catalog.create_namespace(name)
        except Exception:
            # Namespace already exists.
            pass
    return catalog


def _schema(fields: list[tuple[str, object]]) -> Schema:
    return Schema(
        *(
            NestedField(index + 1, name, dtype, required=False)
            for index, (name, dtype) in enumerate(fields)
        )
    )


PRICE_SCHEMA = _schema(
    [
        ("region", StringType()),
        ("interval_end", TimestampType()),
        ("market_date", DateType()),
        ("hour_of_day", IntegerType()),
        ("total_demand_mw", DoubleType()),
        ("rrp", DoubleType()),
        ("period_type", StringType()),
        ("source_month", StringType()),
        ("source_file", StringType()),
    ]
)
SCADA_SCHEMA = _schema(
    [
        ("interval_end", TimestampType()),
        ("market_date", DateType()),
        ("hour_of_day", IntegerType()),
        ("duid", StringType()),
        ("scada_mw", DoubleType()),
        ("source_day", StringType()),
        ("source_file", StringType()),
    ]
)
DUID_SCHEMA = _schema(
    [
        ("duid", StringType()),
        ("region", StringType()),
        ("station_name", StringType()),
        ("participant", StringType()),
        ("dispatch_type", StringType()),
        ("dispatch_class", StringType()),
        ("classification", StringType()),
        ("fuel_primary", StringType()),
        ("fuel_descriptor", StringType()),
        ("technology_primary", StringType()),
        ("technology_descriptor", StringType()),
        ("fuel_group", StringType()),
        ("fuel_chart", StringType()),
        ("reg_cap_mw", DoubleType()),
        ("source_file", StringType()),
    ]
)
CPI_SCHEMA = _schema(
    [
        ("quarter", StringType()),
        ("period_start", DateType()),
        ("index_id", StringType()),
        ("index_name", StringType()),
        ("region_code", StringType()),
        ("region_name", StringType()),
        ("value", DoubleType()),
        ("source_file", StringType()),
    ]
)
CASH_SCHEMA = _schema(
    [
        ("rate_date", DateType()),
        ("cash_rate_target", DoubleType()),
        ("source_file", StringType()),
    ]
)
AUDIT_SCHEMA = _schema(
    [
        ("example_id", StringType()),
        ("label", StringType()),
        ("source_file", StringType()),
    ]
)


def ensure_table(catalog: SqlCatalog, identifier: str, schema: Schema) -> Table:
    try:
        return catalog.load_table(identifier)
    except Exception:
        return catalog.create_table(identifier, schema=schema, properties=_PROPERTIES)


def replace_and_append(table: Table, frame: pa.Table, column: str, values: set[str]) -> int:
    if frame.num_rows == 0:
        return 0
    removed = merge_on_read_replace(table, column, values)
    table.append(frame)
    return removed


def write_table_index(catalog: SqlCatalog, path: Path) -> None:
    rows = []
    for namespace in catalog.list_namespaces():
        ns = namespace[0] if isinstance(namespace, tuple) else namespace
        try:
            identifiers = catalog.list_tables(ns)
        except Exception:
            continue
        for identifier in identifiers:
            name = identifier[-1]
            table = catalog.load_table(identifier)
            rows.append(
                {
                    "schema": ns,
                    "table": name,
                    "location": table.location(),
                    "snapshot": snapshot_delete_counts(table),
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
