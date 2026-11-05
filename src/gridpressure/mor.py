"""Iceberg v2 position-delete commits (merge-on-read).

PyIceberg 0.12 rewrites Parquet when ``Table.delete`` is asked for
merge-on-read. These helpers write spec position-delete files and commit
them in a delete manifest, so scans hide rows without rewriting data files.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import pyarrow as pa
import pyarrow.parquet as pq
from pyiceberg.manifest import (
    DataFile,
    DataFileContent,
    FileFormat,
    ManifestContent,
    ManifestEntry,
    ManifestEntryStatus,
    ManifestWriterV2,
)
from pyiceberg.table import Table
from pyiceberg.table.snapshots import Operation
from pyiceberg.table.update.snapshot import _FastAppendFiles

PATH_FIELD_ID = 2147483546
POS_FIELD_ID = 2147483545

_DELETE_SCHEMA = pa.schema(
    [
        pa.field(
            "file_path",
            pa.string(),
            nullable=False,
            metadata={b"PARQUET:field_id": str(PATH_FIELD_ID).encode()},
        ),
        pa.field(
            "pos",
            pa.int64(),
            nullable=False,
            metadata={b"PARQUET:field_id": str(POS_FIELD_ID).encode()},
        ),
    ]
)


class _PositionDeleteManifestWriter(ManifestWriterV2):
    def content(self) -> ManifestContent:
        return ManifestContent.DELETES

    @property
    def _meta(self) -> dict[str, str]:
        meta = dict(super()._meta)
        meta["content"] = "deletes"
        return meta


class _MergeOnReadAppend(_FastAppendFiles):
    """Append that stores position-delete files in a delete manifest."""

    def _manifests(self):  # type: ignore[no-untyped-def]
        deletes = [
            f for f in self._added_data_files if f.content == DataFileContent.POSITION_DELETES
        ]
        data = [f for f in self._added_data_files if f.content != DataFileContent.POSITION_DELETES]
        self._added_data_files = data
        manifests = super()._manifests()
        self._added_data_files = data + deletes
        if deletes:
            manifests.append(self._write_delete_manifest(deletes))
        return manifests

    def _write_delete_manifest(self, files: list[DataFile]):
        output = self.new_manifest_output()
        writer = _PositionDeleteManifestWriter(
            spec=self._transaction.table_metadata.spec(),
            schema=self.schema(),
            output_file=output,
            snapshot_id=self._snapshot_id,
            avro_compression=self._compression,
        )
        with writer:
            for data_file in files:
                writer.add(
                    ManifestEntry.from_args(
                        status=ManifestEntryStatus.ADDED,
                        snapshot_id=self._snapshot_id,
                        sequence_number=None,
                        data_file=data_file,
                    )
                )
        return writer.to_manifest_file()


def local_path(file_uri: str) -> Path:
    if file_uri.startswith("file:"):
        return Path(unquote(urlparse(file_uri).path))
    return Path(file_uri)


def _summary_dict(snapshot) -> dict[str, str]:
    if snapshot is None or snapshot.summary is None:
        return {}
    summary = snapshot.summary
    props = dict(summary.additional_properties)
    operation = summary.operation
    props["operation"] = str(operation.value if hasattr(operation, "value") else operation)
    keys = (
        "total-position-deletes",
        "added-position-deletes",
        "added-position-delete-files",
        "operation",
    )
    return {key: str(props.get(key, "0")) for key in keys}


def snapshot_delete_counts(table: Table) -> dict[str, str]:
    return _summary_dict(table.current_snapshot())


def position_delete_snapshot(table: Table) -> dict[str, str]:
    """Return the newest snapshot summary that actually added position deletes.

    A later append does not repeat those counters, so the current snapshot can
    show zero even when earlier snapshots are merge-on-read deletes.
    """
    snapshot = table.current_snapshot()
    found = _summary_dict(snapshot)
    while snapshot is not None:
        summary = _summary_dict(snapshot)
        if int(summary.get("added-position-deletes", "0") or 0) > 0:
            return summary
        parent = snapshot.parent_snapshot_id
        snapshot = table.snapshot_by_id(parent) if parent else None
    return found


def _positions_matching(data_path: Path, column: str, values: set[str]) -> list[int]:
    column_table = pq.read_table(data_path, columns=[column])
    return [
        index
        for index, value in enumerate(column_table.column(column).to_pylist())
        if value in values
    ]


def _write_position_delete(table: Table, data_file: DataFile, positions: list[int]) -> DataFile:
    target = data_file.file_path
    arrow = pa.table(
        {
            "file_path": pa.array([target] * len(positions), type=pa.string()),
            "pos": pa.array(positions, type=pa.int64()),
        },
        schema=_DELETE_SCHEMA,
    )
    out_dir = local_path(table.location().rstrip("/")) / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"pos-delete-{uuid.uuid4()}.parquet"
    pq.write_table(arrow, out, compression="zstd", use_dictionary=["file_path"])
    if target.startswith("file:"):
        stored = "file://" + out.as_posix()
    elif "://" in target:
        stored = target.rsplit("/", 1)[0] + "/" + out.name
    else:
        stored = out.as_posix()
    path_bytes = target.encode("utf-8")
    size = out.stat().st_size
    delete_file = DataFile.from_args(
        content=DataFileContent.POSITION_DELETES,
        file_path=stored,
        file_format=FileFormat.PARQUET,
        partition=data_file.partition,
        record_count=len(positions),
        file_size_in_bytes=size,
        column_sizes={PATH_FIELD_ID: size, POS_FIELD_ID: 8 * len(positions)},
        value_counts={PATH_FIELD_ID: len(positions), POS_FIELD_ID: len(positions)},
        null_value_counts={PATH_FIELD_ID: 0, POS_FIELD_ID: 0},
        nan_value_counts={},
        lower_bounds={PATH_FIELD_ID: path_bytes},
        upper_bounds={PATH_FIELD_ID: path_bytes},
        key_metadata=None,
        split_offsets=[4],
        equality_ids=None,
        sort_order_id=None,
    )
    delete_file.spec_id = data_file.spec_id
    return delete_file


def commit_position_deletes(table: Table, delete_files: list[DataFile]) -> dict[str, str]:
    """Commit position-delete files. Existing data files are left in place."""
    if not delete_files:
        return snapshot_delete_counts(table)
    with table.transaction() as tx:
        producer = _MergeOnReadAppend(
            operation=Operation.DELETE,
            transaction=tx,
            io=table.io,
            snapshot_properties={"write.delete.mode": "merge-on-read"},
        )
        with producer as update:
            for delete_file in delete_files:
                update.append_data_file(delete_file)
    table.refresh()
    return snapshot_delete_counts(table)


def merge_on_read_replace(table: Table, column: str, values: set[str]) -> int:
    """Hide rows whose ``column`` is in ``values`` using position deletes.

    Append replacement rows after this returns. Scans that honour Iceberg
    deletes skip the hidden positions and keep later appends.
    """
    if not values:
        return 0
    grouped: dict[str, list[int]] = defaultdict(list)
    files_by_path: dict[str, DataFile] = {}
    for task in table.scan().plan_files():
        data_file = task.file
        files_by_path[data_file.file_path] = data_file
        positions = _positions_matching(local_path(data_file.file_path), column, values)
        if positions:
            grouped[data_file.file_path].extend(positions)
    delete_files: list[DataFile] = []
    removed = 0
    for file_path, positions in grouped.items():
        unique_positions = sorted(set(positions))
        delete_files.append(
            _write_position_delete(table, files_by_path[file_path], unique_positions)
        )
        removed += len(unique_positions)
    commit_position_deletes(table, delete_files)
    return removed
