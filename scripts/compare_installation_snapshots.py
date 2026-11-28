"""Compare logical installation snapshots across repair, upgrade, and variant transitions."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _key(row: dict[str, Any], primary_key: list[str]) -> str:
    if primary_key:
        return json.dumps([row["values"].get(column) for column in primary_key], sort_keys=True)
    return f"rowid:{row['rowid']}"


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    added_tables: list[str] = []
    added_rows: dict[str, int] = {}
    added_columns: dict[str, list[str]] = {}
    for name, old in before["tables"].items():
        new = after["tables"].get(name)
        if new is None:
            errors.append(f"table missing after transition: {name}")
            continue
        shared = [column for column in old["columns"] if column in new["columns"]]
        added = [column for column in new["columns"] if column not in old["columns"]]
        if added:
            added_columns[name] = added
        missing = [column for column in old["columns"] if column not in new["columns"]]
        if missing:
            errors.append(f"columns missing for {name}: {', '.join(missing)}")
        old_rows = {_key(row, old["primary_key"]): row["values"] for row in old["rows"]}
        new_rows = {_key(row, new["primary_key"]): row["values"] for row in new["rows"]}
        missing_rows = sorted(set(old_rows) - set(new_rows))
        if missing_rows:
            errors.append(f"rows missing for {name}: {len(missing_rows)}")
            continue
        added_row_count = len(set(new_rows) - set(old_rows))
        if added_row_count:
            added_rows[name] = added_row_count
        for row_key, old_values in old_rows.items():
            new_values = new_rows[row_key]
            changed = [
                column for column in shared
                if old_values.get(column) != new_values.get(column)
            ]
            if changed:
                errors.append(f"row values changed for {name} key {row_key}: {', '.join(changed)}")
    for name in after["tables"]:
        if name not in before["tables"]:
            added_tables.append(name)

    added_files: list[str] = []
    for relative, old_file in before["files"].items():
        new_file = after["files"].get(relative)
        if new_file is None:
            errors.append(f"file missing after transition: {relative}")
        elif new_file != old_file:
            errors.append(f"file changed after transition: {relative}")
    for relative in after["files"]:
        if relative not in before["files"]:
            added_files.append(relative)
    return {
        "contract": "sentriface.installation-state-comparison",
        "contract_version": 1,
        "status": "FAIL" if errors else "PASS",
        "errors": errors,
        "schema_version_before": before.get("schema_version"),
        "schema_version_after": after.get("schema_version"),
        "added_tables": sorted(added_tables),
        "added_rows": added_rows,
        "added_columns": added_columns,
        "added_files": sorted(added_files),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = compare(
        json.loads(args.before.read_text(encoding="utf-8")),
        json.loads(args.after.read_text(encoding="utf-8")),
    )
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
