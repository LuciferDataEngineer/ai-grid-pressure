"""Parsers for the public files in the snapshot. Values are not invented."""

from __future__ import annotations

import csv
import gzip
import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

import pyarrow as pa

from gridpressure.config import CPI_REGION_NAMES
from gridpressure.fuel import dispatch_class, fuel_chart, fuel_group
from gridpressure.timeutil import hour_of_day, market_date, parse_nem_timestamp

_PRICE = pa.schema(
    [
        ("region", pa.string()),
        ("interval_end", pa.timestamp("us")),
        ("market_date", pa.date32()),
        ("hour_of_day", pa.int32()),
        ("total_demand_mw", pa.float64()),
        ("rrp", pa.float64()),
        ("period_type", pa.string()),
        ("source_month", pa.string()),
        ("source_file", pa.string()),
    ]
)
_SCADA = pa.schema(
    [
        ("interval_end", pa.timestamp("us")),
        ("market_date", pa.date32()),
        ("hour_of_day", pa.int32()),
        ("duid", pa.string()),
        ("scada_mw", pa.float64()),
        ("source_day", pa.string()),
        ("source_file", pa.string()),
    ]
)


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def parse_price_file(path: Path) -> pa.Table:
    region_vals: list[str] = []
    interval_vals: list[datetime] = []
    date_vals = []
    hour_vals: list[int] = []
    demand_vals: list[float] = []
    rrp_vals: list[float] = []
    period_vals: list[str] = []
    month = path.name.split("_")[3] if "_" in path.name else ""
    # PRICE_AND_DEMAND_YYYYMM_REGION.csv.gz -> month is the third token after split
    parts = path.name.replace(".csv.gz", "").replace(".csv", "").split("_")
    month = parts[3] if len(parts) > 3 else month
    source = path.name
    with _open_text(path) as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            period = (row.get("PERIODTYPE") or "").strip()
            if period and period != "TRADE":
                continue
            try:
                moment = parse_nem_timestamp(row["SETTLEMENTDATE"])
                demand = float(row["TOTALDEMAND"])
                price = float(row["RRP"])
            except (KeyError, TypeError, ValueError):
                continue
            if demand < 0:
                continue
            region_vals.append((row.get("REGION") or "").strip())
            interval_vals.append(moment)
            date_vals.append(market_date(moment))
            hour_vals.append(hour_of_day(moment))
            demand_vals.append(demand)
            rrp_vals.append(price)
            period_vals.append(period or "TRADE")
    n = len(region_vals)
    return pa.table(
        {
            "region": region_vals,
            "interval_end": pa.array(interval_vals, type=pa.timestamp("us")),
            "market_date": pa.array(date_vals, type=pa.date32()),
            "hour_of_day": pa.array(hour_vals, type=pa.int32()),
            "total_demand_mw": pa.array(demand_vals, type=pa.float64()),
            "rrp": pa.array(rrp_vals, type=pa.float64()),
            "period_type": period_vals,
            "source_month": [month] * n,
            "source_file": [source] * n,
        },
        schema=_PRICE,
    )


def _iter_aemo_rows(payload: str):
    reader = csv.reader(io.StringIO(payload))
    columns: list[str] | None = None
    family = ""
    for row in reader:
        if not row:
            continue
        kind = row[0]
        if kind == "I" and len(row) > 4:
            family = row[2]
            columns = row[4:]
            continue
        if kind == "D" and columns is not None and len(row) >= 4 + len(columns):
            yield family, dict(zip(columns, row[4 : 4 + len(columns)], strict=False))


def _scada_tables_from_zip(path: Path) -> list[pa.Table]:
    tables: list[pa.Table] = []
    source_day = path.name.replace("PUBLIC_DISPATCHSCADA_", "").replace(".zip", "")
    with zipfile.ZipFile(path) as outer:
        for name in outer.namelist():
            raw = outer.read(name)
            if name.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(raw)) as inner:
                    for inner_name in inner.namelist():
                        text = inner.read(inner_name).decode("utf-8", "replace")
                        table = _scada_rows_to_table(text, source_day, path.name)
                        if table is not None:
                            tables.append(table)
            elif name.lower().endswith(".csv"):
                table = _scada_rows_to_table(raw.decode("utf-8", "replace"), source_day, path.name)
                if table is not None:
                    tables.append(table)
    return tables


def _scada_rows_to_table(text: str, source_day: str, source_file: str) -> pa.Table | None:
    moments: list[datetime] = []
    dates = []
    hours: list[int] = []
    duids: list[str] = []
    values: list[float] = []
    for family, row in _iter_aemo_rows(text):
        if family != "UNIT_SCADA":
            continue
        duid = (row.get("DUID") or "").strip()
        if not duid:
            continue
        try:
            moment = parse_nem_timestamp(row["SETTLEMENTDATE"])
            megawatts = float(row["SCADAVALUE"])
        except (KeyError, TypeError, ValueError):
            continue
        moments.append(moment)
        dates.append(market_date(moment))
        hours.append(hour_of_day(moment))
        duids.append(duid)
        values.append(megawatts)
    if not duids:
        return None
    n = len(duids)
    return pa.table(
        {
            "interval_end": pa.array(moments, type=pa.timestamp("us")),
            "market_date": pa.array(dates, type=pa.date32()),
            "hour_of_day": pa.array(hours, type=pa.int32()),
            "duid": duids,
            "scada_mw": pa.array(values, type=pa.float64()),
            "source_day": [source_day] * n,
            "source_file": [source_file] * n,
        },
        schema=_SCADA,
    )


def parse_scada_day(path: Path) -> pa.Table:
    tables = _scada_tables_from_zip(path)
    if not tables:
        return pa.table(
            {name: [] for name in _SCADA.names},
            schema=_SCADA,
        )
    return pa.concat_tables(tables)


def _header_map(header: tuple) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, cell in enumerate(header):
        key = " ".join(str(cell or "").replace("\n", " ").split()).strip().lower()
        if key and key not in mapping:
            mapping[key] = index
    return mapping


def _cell(row: tuple, mapping: dict[str, int], name: str) -> str:
    index = mapping.get(name)
    if index is None or index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _float_or_none(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_registry(path: Path) -> pa.Table:
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook["PU and Scheduled Loads"]
    rows = sheet.iter_rows(values_only=True)
    header = next(rows)
    mapping = _header_map(header)
    records: dict[str, dict] = {}
    for row in rows:
        duid = _cell(row, mapping, "duid")
        if not duid or duid.lower() == "duid":
            continue
        primary = _cell(row, mapping, "fuel source - primary")
        descriptor = _cell(row, mapping, "fuel source - descriptor")
        technology = _cell(row, mapping, "technology type - primary")
        tech_desc = _cell(row, mapping, "technology type - descriptor")
        dispatch = _cell(row, mapping, "dispatch type")
        group = fuel_group(primary, technology, descriptor)
        cap = _float_or_none(_cell(row, mapping, "reg cap generation (mw)"))
        candidate = {
            "duid": duid,
            "region": _cell(row, mapping, "region"),
            "station_name": _cell(row, mapping, "station name"),
            "participant": _cell(row, mapping, "participant"),
            "dispatch_type": dispatch,
            "dispatch_class": dispatch_class(dispatch),
            "classification": _cell(row, mapping, "classification"),
            "fuel_primary": primary,
            "fuel_descriptor": descriptor,
            "technology_primary": technology,
            "technology_descriptor": tech_desc,
            "fuel_group": group,
            "fuel_chart": fuel_chart(primary, group, descriptor),
            "reg_cap_mw": cap,
            "source_file": path.name,
        }
        current = records.get(duid)
        if current is None or _prefer(candidate, current):
            records[duid] = candidate
    workbook.close()
    columns = (
        list(next(iter(records.values())).keys())
        if records
        else [
            "duid",
            "region",
            "station_name",
            "participant",
            "dispatch_type",
            "dispatch_class",
            "classification",
            "fuel_primary",
            "fuel_descriptor",
            "technology_primary",
            "technology_descriptor",
            "fuel_group",
            "fuel_chart",
            "reg_cap_mw",
            "source_file",
        ]
    )
    data = {name: [row[name] for row in records.values()] for name in columns}
    data["reg_cap_mw"] = pa.array(data["reg_cap_mw"], type=pa.float64())
    return pa.table(data)


def _prefer(new: dict, old: dict) -> bool:
    rank = {"generating": 3, "bidirectional": 2, "other": 1, "load": 0, "unclassified": 0}
    if rank.get(new["dispatch_class"], 0) != rank.get(old["dispatch_class"], 0):
        return rank.get(new["dispatch_class"], 0) > rank.get(old["dispatch_class"], 0)
    return (new["reg_cap_mw"] or 0) > (old["reg_cap_mw"] or 0)


def parse_cpi_json(path: Path) -> pa.Table:
    document = json.loads(path.read_text(encoding="utf-8"))
    dataset = document["data"]["dataSets"][0]
    observations = dataset["observations"]
    dimensions = document["data"]["structures"][0]["dimensions"]["observation"]
    by_id = {dim["id"]: dim["values"] for dim in dimensions}
    quarters: list[str] = []
    starts = []
    index_ids: list[str] = []
    index_names: list[str] = []
    region_codes: list[str] = []
    region_names: list[str] = []
    values: list[float] = []
    for key, payload in observations.items():
        indexes = [int(part) for part in key.split(":")]
        if len(indexes) != len(dimensions):
            continue
        coded = {}
        for dim, index in zip(dimensions, indexes, strict=True):
            coded[dim["id"]] = dim["values"][index]
        if coded.get("MEASURE", {}).get("id") != "1":
            continue
        quarter = coded["TIME_PERIOD"]["id"]
        index_id = coded["INDEX"]["id"]
        region = coded["REGION"]["id"]
        raw = payload[0] if isinstance(payload, list) else payload
        if raw is None:
            continue
        quarters.append(quarter)
        starts.append(_quarter_start(quarter))
        index_ids.append(index_id)
        index_names.append(coded["INDEX"].get("name") or index_id)
        region_codes.append(region)
        region_names.append(CPI_REGION_NAMES.get(region, coded["REGION"].get("name") or region))
        values.append(float(raw))
    del by_id
    return pa.table(
        {
            "quarter": quarters,
            "period_start": pa.array(starts, type=pa.date32()),
            "index_id": index_ids,
            "index_name": index_names,
            "region_code": region_codes,
            "region_name": region_names,
            "value": pa.array(values, type=pa.float64()),
            "source_file": [path.name] * len(quarters),
        }
    )


def _quarter_start(quarter: str):
    year, q = quarter.split("-Q")
    month = (int(q) - 1) * 3 + 1
    return datetime(int(year), month, 1).date()


def parse_cash_rate(path: Path) -> pa.Table:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    dates = []
    rates: list[float] = []
    for line in lines:
        if not line or not line[0].isdigit():
            continue
        parts = line.split(",")
        if len(parts) < 2 or not parts[1].strip():
            continue
        try:
            moment = datetime.strptime(parts[0].strip(), "%d-%b-%Y").date()
            rate = float(parts[1])
        except ValueError:
            continue
        dates.append(moment)
        rates.append(rate)
    return pa.table(
        {
            "rate_date": pa.array(dates, type=pa.date32()),
            "cash_rate_target": pa.array(rates, type=pa.float64()),
            "source_file": [path.name] * len(dates),
        }
    )
