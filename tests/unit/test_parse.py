import gzip
import io
import zipfile
from pathlib import Path

from gridpressure.parse import parse_price_file, parse_scada_day


def test_price_file_parses_trade_intervals(tmp_path: Path):
    raw = (
        "REGION,SETTLEMENTDATE,TOTALDEMAND,RRP,PERIODTYPE\n"
        "NSW1,2026/11/04 00:05:00,7000.5,80.5,TRADE\n"
        "NSW1,2026/11/04 24:00:00,6900,120.25,TRADE\n"
        "NSW1,2026/11/04 00:10:00,1,1,FORECAST\n"
    )
    path = tmp_path / "PRICE_AND_DEMAND_202611_NSW1.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(raw)
    table = parse_price_file(path)
    assert table.num_rows == 2
    assert table.column("source_month").to_pylist() == ["202611", "202611"]
    assert table.column("market_date").to_pylist()[1].isoformat() == "2026-11-04"
    assert table.column("hour_of_day").to_pylist()[1] == 23


def test_nested_scada_zip(tmp_path: Path):
    csv_text = (
        "C,NEMP.WORLD,DISPATCHSCADA,AEMO,PUBLIC,2026/11/04,00:00:15,1,DISPATCHSCADA,1\n"
        "I,DISPATCH,UNIT_SCADA,1,SETTLEMENTDATE,DUID,SCADAVALUE,LASTCHANGED\n"
        'D,DISPATCH,UNIT_SCADA,1,"2026/11/04 00:05:00",BARCSF1,1.5,"2026/11/04 00:00:14"\n'
        "C,END OF REPORT,4\n"
    )
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("PUBLIC_DISPATCHSCADA_202611040005.CSV", csv_text)
    path = tmp_path / "PUBLIC_DISPATCHSCADA_20261104.zip"
    with zipfile.ZipFile(path, "w") as outer:
        outer.writestr("PUBLIC_DISPATCHSCADA_202611040005.zip", inner.getvalue())
    table = parse_scada_day(path)
    assert table.num_rows == 1
    assert table.column("duid").to_pylist() == ["BARCSF1"]
    assert table.column("scada_mw").to_pylist() == [1.5]
    assert table.column("source_day").to_pylist() == ["20261104"]
