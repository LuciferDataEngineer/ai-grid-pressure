import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.schema import Schema
from pyiceberg.types import DoubleType, NestedField, StringType

from gridpressure.mor import merge_on_read_replace, snapshot_delete_counts


def test_position_deletes_hide_rows_without_rewriting(tmp_path):
    warehouse = tmp_path / "warehouse"
    catalog = SqlCatalog(
        "grid",
        **{"uri": f"sqlite:///{tmp_path / 'catalog.db'}", "warehouse": str(warehouse)},
    )
    catalog.create_namespace("silver")
    schema = Schema(
        NestedField(1, "region", StringType(), required=False),
        NestedField(2, "source_file", StringType(), required=False),
        NestedField(3, "mw", DoubleType(), required=False),
    )
    table = catalog.create_table(
        "silver.demo",
        schema=schema,
        properties={"write.delete.mode": "merge-on-read"},
    )
    table.append(
        pa.table(
            {
                "region": ["NSW1", "QLD1", "VIC1"],
                "source_file": ["a.csv", "a.csv", "b.csv"],
                "mw": [1.0, 2.0, 3.0],
            }
        )
    )
    data_files_before = {task.file.file_path for task in table.scan().plan_files()}
    removed = merge_on_read_replace(table, "source_file", {"a.csv"})
    assert removed == 2
    live = table.scan().to_arrow().to_pydict()
    assert live["source_file"] == ["b.csv"]
    summary = snapshot_delete_counts(table)
    assert summary["added-position-deletes"] == "2"
    assert int(summary["added-position-delete-files"]) >= 1
    data_files_after = {
        task.file.file_path
        for task in table.scan().plan_files()
        if task.file.file_path.endswith(".parquet") and "pos-delete" not in task.file.file_path
    }
    assert data_files_before == data_files_after
