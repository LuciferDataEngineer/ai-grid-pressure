import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "docs" / "data" / "dashboard.json"
BANNED = (
    "iceberg",
    "dagster",
    "duckdb",
    "trino",
    "marquez",
    "openlineage",
    "parquet",
    "great expectations",
    "pipeline",
    "schema",
    "warehouse",
    "bronze",
    "silver",
    "scada",
    "duid",
    "rrp",
    "dbt",
)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def test_dashboard_is_plain_english_and_tabbed():
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    labels = [tab["label"] for tab in payload["tabs"]]
    assert labels == [
        "Overview",
        "Demand stress",
        "Prices",
        "Fuel mix",
        "Bills & CPI",
        "Actions",
    ]
    for tab in payload["tabs"]:
        assert 3 <= len(tab["kpis"]) <= 5
        assert len(tab["charts"]) <= 3
        assert tab["meaning"]
        assert tab["sources"]
    blob = "\n".join(_strings(payload)).lower()
    for word in BANNED:
        assert word not in blob, word


def test_merge_on_read_evidence_and_docs():
    evidence = json.loads((ROOT / "docs" / "evidence" / "iceberg_mor.json").read_text())
    assert int(evidence["audit_snapshot"]["added-position-deletes"]) >= 1
    assert "hidden" not in evidence["audit_live_labels"]
    assert (ROOT / "docs" / "gx" / "index.html").exists()
    events = json.loads((ROOT / "docs" / "lineage" / "events.json").read_text())
    assert len(events) >= 4
    assert (ROOT / "docs" / "lineage" / "lineage.svg").exists()
    assert (ROOT / "INSIGHTS.md").exists()
    assert (ROOT / "data" / "snapshot" / "manifest.json").exists()
