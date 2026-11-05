"""Paths, source URLs, and analysis markers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "snapshot"
WAREHOUSE = ROOT / "data" / "warehouse"
ICEBERG_DIR = WAREHOUSE / "iceberg"
CATALOG_DB = WAREHOUSE / "catalog.db"
DUCKDB_PATH = WAREHOUSE / "grid.duckdb"
DOCS = ROOT / "docs"
GX_DIR = ROOT / "gx"
DBT_DIR = ROOT / "dbt"
DASHBOARD_DIR = ROOT / "dashboard"

USER_AGENT = "ai-grid-pressure/1.0 (public-data research; no API key)"

REGIONS = ("NSW1", "QLD1", "VIC1", "SA1", "TAS1")
REGION_NAMES = {
    "NSW1": "New South Wales",
    "QLD1": "Queensland",
    "VIC1": "Victoria",
    "SA1": "South Australia",
    "TAS1": "Tasmania",
}
CPI_REGION_NAMES = {
    "50": "Australia",
    "1": "Sydney",
    "2": "Melbourne",
    "3": "Brisbane",
    "4": "Adelaide",
    "6": "Hobart",
    "8": "Canberra",
}

# Analysis marker used in Australian Energy Regulator wholesale reporting.
HIGH_PRICE_AUD = 300.0
EXTREME_PRICE_AUD = 5000.0

PRICE_START = (2024, 11)
PRICE_END = (2026, 11)
SCADA_START = date(2026, 10, 22)
SCADA_END = date(2026, 11, 4)

AEMO_PRICE_URL = (
    "https://aemo.com.au/aemo/data/nem/priceanddemand/PRICE_AND_DEMAND_{yyyymm}_{region}.csv"
)
AEMO_SCADA_URL = (
    "https://nemweb.com.au/Reports/ARCHIVE/Dispatch_SCADA/PUBLIC_DISPATCHSCADA_{yyyymmdd}.zip"
)
AEMO_REGISTRY_URL = (
    "https://www.aemo.com.au/-/media/files/electricity/nem/"
    "participant_information/nem-registration-and-exemption-list.xlsx"
)
ABS_CPI_URL = "https://data.api.abs.gov.au/rest/data/ABS,CPI,2.0.0/{key}"
RBA_F1_URL = "https://www.rba.gov.au/statistics/tables/csv/f1-data.csv"

OPENLINEAGE_NAMESPACE = "ai-grid-pressure"
PRODUCER = "https://github.com/LuciferDataEngineer/ai-grid-pressure"
SCHEMA_URL = "https://openlineage.io/spec/2-0-2/OpenLineage.json"
