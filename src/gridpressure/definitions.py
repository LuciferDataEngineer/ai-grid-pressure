"""Dagster assets. Each asset emits an OpenLineage complete event."""

from dagster import Definitions, asset

from gridpressure.ingest import ensure_snapshot
from gridpressure.lineage import emit
from gridpressure.pipeline import build_lake


@asset(group_name="ingest")
def public_snapshot() -> str:
    path = ensure_snapshot(refresh=False)
    emit(
        "public_snapshot",
        ["aemo.price_and_demand", "aemo.dispatch_scada", "aemo.registration", "abs.cpi", "rba.f1"],
        ["snapshot.manifest"],
    )
    return str(path)


@asset(group_name="lakehouse")
def lakehouse(public_snapshot: str) -> dict:
    stats = build_lake()
    emit(
        "iceberg_bronze_silver",
        [
            "snapshot.price_demand",
            "snapshot.scada",
            "snapshot.registry",
            "snapshot.cpi",
            "snapshot.cash_rate",
        ],
        [
            "bronze.price_demand",
            "silver.price_interval",
            "bronze.unit_scada",
            "silver.unit_scada",
            "silver.duid",
            "silver.cpi",
            "silver.cash_rate",
            "ops.mor_audit",
        ],
    )
    stats["snapshot"] = public_snapshot
    return stats


@asset(group_name="marts")
def gold_marts(lakehouse: dict) -> dict:
    from gridpressure.config import WAREHOUSE
    from gridpressure.iceberg_store import open_catalog, write_table_index
    from gridpressure.warehouse import build_marts, export_gold_iceberg

    catalog = open_catalog()
    counts = build_marts(catalog)
    gold = export_gold_iceberg(catalog)
    write_table_index(catalog, WAREHOUSE / "iceberg_tables.json")
    emit(
        "duckdb_gold_marts",
        [
            "silver.price_interval",
            "silver.unit_scada",
            "silver.duid",
            "silver.cpi",
            "silver.cash_rate",
        ],
        gold,
    )
    return {"rows": counts, "lakehouse": lakehouse, "gold": gold}


@asset(group_name="quality")
def data_quality(gold_marts: dict) -> str:
    from gridpressure.quality import validate_and_document

    path = validate_and_document()
    emit("data_quality", ["silver.price_interval", "gold.mart_region_day"], ["docs.gx"])
    return str(path)


@asset(group_name="publish")
def briefing_site(gold_marts: dict, data_quality: str) -> dict:
    from gridpressure.narrative import build_briefing, write_documents

    payload = build_briefing()
    write_documents(payload)
    emit(
        "briefing_site",
        ["gold.mart_region_day", "gold.mart_cpi", "gold.mart_cash"],
        ["docs.dashboard"],
    )
    return {
        "tabs": [tab["id"] for tab in payload["dashboard"]["tabs"]],
        "quality": data_quality,
        "marts": gold_marts["gold"],
    }


defs = Definitions(assets=[public_snapshot, lakehouse, gold_marts, data_quality, briefing_site])
