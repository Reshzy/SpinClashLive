"""Fail if generated OpenAPI/TS contracts are stale."""

from __future__ import annotations

import json
from pathlib import Path

from export_contracts import openapi_to_ts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    from color_rush.api.app import create_app

    schema = create_app().openapi()
    expected_json = json.dumps(schema, indent=2) + "\n"
    expected_ts = openapi_to_ts(schema)
    actual_json = (ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
    actual_ts = (ROOT / "contracts" / "ts" / "api.d.ts").read_text(encoding="utf-8")
    if actual_json != expected_json or actual_ts != expected_ts:
        raise SystemExit("contracts are stale; run: uv run python scripts/export_contracts.py")
    print("contracts ok")


if __name__ == "__main__":
    main()
