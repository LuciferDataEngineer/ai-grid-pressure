"""Checksum manifest for the committed public-data snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from gridpressure.config import SNAPSHOT


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(entries: list[dict]) -> Path:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    document = {
        "project": "ai-grid-pressure",
        "description": (
            "Reproducible extract of free public AEMO, ABS and RBA files. "
            "No values in this snapshot were invented."
        ),
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "files": entries,
    }
    target = SNAPSHOT / "manifest.json"
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return target


def load_manifest() -> dict:
    return json.loads((SNAPSHOT / "manifest.json").read_text(encoding="utf-8"))
