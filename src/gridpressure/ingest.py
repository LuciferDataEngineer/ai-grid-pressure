"""Download free public files into the committed snapshot."""

from __future__ import annotations

import gzip
import logging
from datetime import date, timedelta
from pathlib import Path

import requests

from gridpressure.config import (
    ABS_CPI_URL,
    AEMO_PRICE_URL,
    AEMO_REGISTRY_URL,
    AEMO_SCADA_URL,
    PRICE_END,
    PRICE_START,
    RBA_F1_URL,
    REGIONS,
    SCADA_END,
    SCADA_START,
    SNAPSHOT,
    USER_AGENT,
)
from gridpressure.manifest import sha256_file, write_manifest

log = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


def _months(start: tuple[int, int], end: tuple[int, int]) -> list[str]:
    year, month = start
    values: list[str] = []
    while (year, month) <= end:
        values.append(f"{year}{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return values


def _days(start: date, end: date) -> list[date]:
    values = []
    cursor = start
    while cursor <= end:
        values.append(cursor)
        cursor += timedelta(days=1)
    return values


def _download(url: str, target: Path, refresh: bool) -> None:
    if target.exists() and not refresh:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    log.info("downloading %s", url)
    response = _SESSION.get(url, timeout=180)
    response.raise_for_status()
    if target.suffix == ".gz" and not url.endswith(".gz"):
        with gzip.open(target, "wb") as handle:
            handle.write(response.content)
    else:
        target.write_bytes(response.content)


def _entry(path: Path, url: str, publisher: str, licence_name: str) -> dict:
    relative = path.relative_to(SNAPSHOT.parent.parent).as_posix()
    return {
        "path": relative,
        "url": url,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "publisher": publisher,
        "licence": licence_name,
        "accessed_at": date.today().isoformat(),
    }


def ensure_snapshot(refresh: bool = False) -> Path:
    """Fetch any missing snapshot files and rewrite the checksum manifest."""
    entries: list[dict] = []
    price_dir = SNAPSHOT / "price_demand"
    for yyyymm in _months(PRICE_START, PRICE_END):
        for region in REGIONS:
            name = f"PRICE_AND_DEMAND_{yyyymm}_{region}.csv.gz"
            url = AEMO_PRICE_URL.format(yyyymm=yyyymm, region=region)
            path = price_dir / name
            _download(url, path, refresh)
            entries.append(
                _entry(
                    path,
                    url,
                    "AEMO",
                    "AEMO public NEM price and demand file. Free anonymous HTTP. Attribute AEMO.",
                )
            )
    scada_dir = SNAPSHOT / "scada"
    for day in _days(SCADA_START, SCADA_END):
        stamp = day.strftime("%Y%m%d")
        url = AEMO_SCADA_URL.format(yyyymmdd=stamp)
        path = scada_dir / f"PUBLIC_DISPATCHSCADA_{stamp}.zip"
        _download(url, path, refresh)
        entries.append(
            _entry(
                path,
                url,
                "AEMO",
                "AEMO public dispatch SCADA archive. Free anonymous HTTP. Attribute AEMO.",
            )
        )
    registry = SNAPSHOT / "reference" / "nem-registration-and-exemption-list.xlsx"
    _download(AEMO_REGISTRY_URL, registry, refresh)
    entries.append(
        _entry(
            registry,
            AEMO_REGISTRY_URL,
            "AEMO",
            "AEMO NEM Registration and Exemption List. Free download. Attribute AEMO.",
        )
    )
    abs_dir = SNAPSHOT / "abs"
    cpi_specs = {
        "cpi_electricity_australia.json": "1.40055.10.50.Q",
        "cpi_all_groups_capitals.json": "1.10001.10.50+1+2+3+4+6+8.Q",
    }
    for name, key in cpi_specs.items():
        url = (
            ABS_CPI_URL.format(key=key.replace("+", "%2B"))
            + "?startPeriod=2016-Q1&dimensionAtObservation=AllDimensions"
        )
        path = abs_dir / name
        if refresh or not path.exists():
            log.info("downloading %s", url)
            response = _SESSION.get(
                url,
                timeout=180,
                headers={"Accept": "application/vnd.sdmx.data+json"},
            )
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
        entries.append(
            _entry(
                path,
                url,
                "ABS",
                "Australian Bureau of Statistics CPI. Free SDMX API. ABS CC BY 4.0.",
            )
        )
    rba = SNAPSHOT / "rba" / "f1-data.csv"
    _download(RBA_F1_URL, rba, refresh)
    entries.append(
        _entry(
            rba,
            RBA_F1_URL,
            "RBA",
            "Reserve Bank of Australia statistical table F1. Free CSV. Attribute the RBA.",
        )
    )
    return write_manifest(entries)
