"""Ingest the snapshot and land bronze, silver, and the merge-on-read audit."""

from __future__ import annotations

import json
import logging

import pyarrow as pa

from gridpressure.config import DOCS, SNAPSHOT, WAREHOUSE
from gridpressure.iceberg_store import (
    AUDIT_SCHEMA,
    CASH_SCHEMA,
    CPI_SCHEMA,
    DUID_SCHEMA,
    PRICE_SCHEMA,
    SCADA_SCHEMA,
    ensure_table,
    open_catalog,
    replace_and_append,
    write_table_index,
)
from gridpressure.ingest import ensure_snapshot
from gridpressure.mor import position_delete_snapshot
from gridpressure.parse import (
    parse_cash_rate,
    parse_cpi_json,
    parse_price_file,
    parse_registry,
    parse_scada_day,
)

log = logging.getLogger(__name__)


def _reset(catalog, identifier: str, schema):
    try:
        catalog.drop_table(identifier)
    except Exception:
        pass
    return ensure_table(catalog, identifier, schema)


def _concat(frames: list[pa.Table]) -> pa.Table:
    present = [frame for frame in frames if frame.num_rows]
    if not present:
        raise RuntimeError("No rows were parsed")
    return pa.concat_tables(present)


def build_lake() -> dict:
    ensure_snapshot(refresh=False)
    catalog = open_catalog()
    price_paths = sorted((SNAPSHOT / "price_demand").glob("*.csv.gz"))
    scada_paths = sorted((SNAPSHOT / "scada").glob("*.zip"))
    if not price_paths or not scada_paths:
        raise RuntimeError("Snapshot is missing price or SCADA files. Run ingest first.")

    bronze_price = _reset(catalog, "bronze.price_demand", PRICE_SCHEMA)
    silver_price = _reset(catalog, "silver.price_interval", PRICE_SCHEMA)
    for path in price_paths:
        frame = parse_price_file(path)
        log.info("price %s rows %s", path.name, frame.num_rows)
        bronze_price.append(frame)
        silver_price.append(frame)

    # Reload one real month with position deletes so the silver table itself
    # carries a merge-on-read snapshot, not only the tiny audit table.
    reload_name = price_paths[-1].name
    reload_frame = parse_price_file(price_paths[-1])
    removed = replace_and_append(silver_price, reload_frame, "source_file", {reload_name})
    log.info("merge-on-read reloaded %s, positions hidden %s", reload_name, removed)

    bronze_scada = _reset(catalog, "bronze.unit_scada", SCADA_SCHEMA)
    silver_scada = _reset(catalog, "silver.unit_scada", SCADA_SCHEMA)
    for path in scada_paths:
        frame = parse_scada_day(path)
        log.info("scada %s rows %s", path.name, frame.num_rows)
        bronze_scada.append(frame)
        silver_scada.append(frame)

    registry = parse_registry(SNAPSHOT / "reference" / "nem-registration-and-exemption-list.xlsx")
    duid = _reset(catalog, "silver.duid", DUID_SCHEMA)
    duid.append(registry)

    cpi_frames = [parse_cpi_json(path) for path in sorted((SNAPSHOT / "abs").glob("*.json"))]
    cpi = _reset(catalog, "silver.cpi", CPI_SCHEMA)
    cpi.append(_concat(cpi_frames))

    cash = _reset(catalog, "silver.cash_rate", CASH_SCHEMA)
    cash.append(parse_cash_rate(SNAPSHOT / "rba" / "f1-data.csv"))

    audit = _reset(catalog, "ops.mor_audit", AUDIT_SCHEMA)
    demo = pa.table(
        {
            "example_id": ["1", "2", "3"],
            "label": ["kept", "hidden", "kept"],
            "source_file": ["demo-keep", "demo-hide", "demo-keep"],
        }
    )
    audit.append(demo)
    audit_removed = replace_and_append(
        audit,
        pa.table(
            {
                "example_id": ["4"],
                "label": ["added-after-delete"],
                "source_file": ["demo-new"],
            }
        ),
        "source_file",
        {"demo-hide"},
    )
    live = audit.scan().to_arrow().column("label").to_pylist()
    evidence = {
        "method": "Iceberg v2 position delete files committed in a delete manifest",
        "note": (
            "PyIceberg 0.12 Table.delete still rewrites Parquet. "
            "This project writes position-delete files so reads skip rows without "
            "rewriting the data files."
        ),
        "audit_positions_hidden": audit_removed,
        "audit_live_labels": live,
        "audit_snapshot": position_delete_snapshot(audit),
        "silver_price_reload": {
            "source_file": reload_name,
            "positions_hidden": removed,
            "snapshot": position_delete_snapshot(silver_price),
        },
    }
    evidence_path = DOCS / "evidence" / "iceberg_mor.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    write_table_index(catalog, WAREHOUSE / "iceberg_tables.json")
    return {
        "price_files": len(price_paths),
        "scada_files": len(scada_paths),
        "duid_rows": registry.num_rows,
        "mor_hidden_on_reload": removed,
        "audit_live_labels": live,
    }
