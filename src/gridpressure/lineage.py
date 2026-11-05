"""OpenLineage events, written locally and posted to Marquez when configured."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

from gridpressure.config import DOCS, OPENLINEAGE_NAMESPACE, PRODUCER, SCHEMA_URL

_EVENTS: list[dict] = []


def emit(name: str, inputs: list[str], outputs: list[str]) -> dict:
    event = {
        "eventType": "COMPLETE",
        "eventTime": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run": {"runId": str(uuid.uuid4())},
        "job": {"namespace": OPENLINEAGE_NAMESPACE, "name": name},
        "inputs": [{"namespace": OPENLINEAGE_NAMESPACE, "name": item} for item in inputs],
        "outputs": [{"namespace": OPENLINEAGE_NAMESPACE, "name": item} for item in outputs],
        "producer": PRODUCER,
        "schemaURL": SCHEMA_URL,
    }
    _EVENTS.append(event)
    _write()
    url = os.environ.get("OPENLINEAGE_URL", "").strip()
    if url:
        request = urllib.request.Request(
            url.rstrip("/") + "/api/v1/lineage",
            data=json.dumps(event).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=10).read()
        except urllib.error.URLError as exc:
            print(f"OpenLineage post failed for {name}: {exc}")
    return event


def _write() -> None:
    folder = DOCS / "lineage"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "events.json").write_text(json.dumps(_EVENTS, indent=2) + "\n", encoding="utf-8")
    (folder / "lineage.svg").write_text(_svg(_EVENTS), encoding="utf-8")


def _svg(events: list[dict]) -> str:
    width = 760
    row = 64
    height = 80 + row * max(len(events), 1)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#f4f0e6"/>',
        '<text x="24" y="36" font-family="Georgia, serif" font-size="20" fill="#1a2332">OpenLineage jobs</text>',
    ]
    for index, event in enumerate(events):
        y = 56 + index * row
        name = event["job"]["name"]
        inputs = ", ".join(item["name"] for item in event["inputs"]) or "—"
        outputs = ", ".join(item["name"] for item in event["outputs"]) or "—"
        parts.append(
            f'<rect x="24" y="{y}" width="712" height="52" rx="8" fill="#fffdf8" stroke="#e4dccb"/>'
        )
        parts.append(
            f'<text x="40" y="{y + 22}" font-family="Georgia, serif" font-size="16" fill="#0e6b62">{_xml(name)}</text>'
        )
        parts.append(
            f'<text x="40" y="{y + 40}" font-family="sans-serif" font-size="12" fill="#1a2332">'
            f"{_xml(inputs)} → {_xml(outputs)}</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def _xml(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
