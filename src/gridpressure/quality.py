"""Great Expectations suites for silver and gold tables."""

from __future__ import annotations

import shutil

import duckdb
import pandas as pd

from gridpressure.config import DOCS, DUCKDB_PATH, GX_DIR, REGIONS


def _frame(sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def _expectations():
    from great_expectations.expectations import (
        ExpectColumnMinToBeBetween,
        ExpectColumnPairValuesAToBeGreaterThanB,
        ExpectColumnValuesToBeBetween,
        ExpectColumnValuesToBeInSet,
        ExpectColumnValuesToNotBeNull,
    )

    return {
        "not_null": ExpectColumnValuesToNotBeNull,
        "in_set": ExpectColumnValuesToBeInSet,
        "between": ExpectColumnValuesToBeBetween,
        "min_between": ExpectColumnMinToBeBetween,
        "pair": ExpectColumnPairValuesAToBeGreaterThanB,
    }


def _asset(source, name: str):
    try:
        return source.get_asset(name)
    except Exception:
        return source.add_dataframe_asset(name)


def _batch(asset):
    try:
        return asset.get_batch_definition("whole")
    except Exception:
        return asset.add_batch_definition_whole_dataframe("whole")


def _run(context, gx, name: str, frame: pd.DataFrame, expectations: list) -> None:
    try:
        source = context.data_sources.get("pandas_source")
    except Exception:
        source = context.data_sources.add_pandas("pandas_source")
    asset = _asset(source, name)
    batch = _batch(asset)
    for collection, key in (
        (context.suites, name),
        (context.validation_definitions, f"{name}_check"),
    ):
        try:
            collection.delete(key)
        except Exception:
            pass
    suite = context.suites.add(gx.ExpectationSuite(name=name))
    for expectation in expectations:
        suite.add_expectation(expectation)
    validation = context.validation_definitions.add(
        gx.ValidationDefinition(name=f"{name}_check", data=batch, suite=suite)
    )
    result = validation.run(batch_parameters={"dataframe": frame})
    if not result.success:
        raise RuntimeError(f"Data quality checks failed for {name}")


def validate_and_document():
    import great_expectations as gx

    builders = _expectations()
    if GX_DIR.exists():
        shutil.rmtree(GX_DIR)
    GX_DIR.mkdir(parents=True, exist_ok=True)
    context = gx.get_context(mode="file", context_root_dir=str(GX_DIR))
    _run(
        context,
        gx,
        "silver_price",
        _frame("SELECT region, total_demand_mw, rrp FROM silver_price"),
        [
            builders["not_null"](column="region"),
            builders["in_set"](column="region", value_set=list(REGIONS)),
            builders["not_null"](column="total_demand_mw"),
            builders["not_null"](column="rrp"),
            builders["between"](column="total_demand_mw", min_value=0, max_value=30000),
            builders["between"](column="rrp", min_value=-2000, max_value=25000),
        ],
    )
    _run(
        context,
        gx,
        "silver_scada",
        _frame("SELECT duid, scada_mw FROM silver_scada"),
        [
            builders["not_null"](column="duid"),
            builders["not_null"](column="scada_mw"),
            builders["between"](column="scada_mw", min_value=-5000, max_value=5000),
        ],
    )
    _run(
        context,
        gx,
        "gold_region_day",
        _frame(
            """
            SELECT region, intervals, peak_mw, avg_mw, min_mw
            FROM mart_region_day
            """
        ),
        [
            builders["not_null"](column="region"),
            builders["in_set"](column="region", value_set=list(REGIONS)),
            builders["between"](column="intervals", min_value=1, max_value=300),
            builders["min_between"](column="peak_mw", min_value=0),
            builders["pair"](column_A="peak_mw", column_B="avg_mw", or_equal=True),
            builders["pair"](column_A="avg_mw", column_B="min_mw", or_equal=True),
        ],
    )
    _run(
        context,
        gx,
        "gold_fuel",
        _frame("SELECT fuel_group, mwh FROM mart_fuel_day"),
        [
            builders["in_set"](
                column="fuel_group",
                value_set=["renewable", "fossil", "storage", "other", "unclassified"],
            ),
            builders["min_between"](column="mwh", min_value=0),
        ],
    )
    _run(
        context,
        gx,
        "gold_cpi",
        _frame("SELECT value FROM mart_cpi"),
        [builders["between"](column="value", min_value=1, max_value=500)],
    )
    context.build_data_docs()
    site = GX_DIR / "uncommitted" / "data_docs" / "local_site"
    target = DOCS / "gx"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(site, target)
    return target
