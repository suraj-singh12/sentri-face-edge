"""Capture a logical, key-verified snapshot of a SentriFace installation data root."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from sentriface.secure_storage import KEYRING_SERVICE, _keyring_account


def _load_existing_key(data_dir: Path) -> bytes:
    import keyring

    encoded = keyring.get_password(KEYRING_SERVICE, _keyring_account(data_dir))
    if not encoded:
        raise RuntimeError("No SentriFace storage key exists for this data directory")
    key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    if len(key) != 32:
        raise RuntimeError("Stored SentriFace storage key is invalid")
    return key


def _value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"__blob__": base64.b64encode(value).decode("ascii")}
    return value


def capture(data_dir: Path) -> dict[str, Any]:
    data_dir = data_dir.resolve()
    database = data_dir / "sentriface.db"
    if not database.is_file():
        raise RuntimeError(f"Encrypted database is missing: {database}")
    key = _load_existing_key(data_dir)
    from sqlcipher3 import dbapi2

    connection = dbapi2.connect(str(database), timeout=30)
    connection.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
    tables: dict[str, Any] = {}
    try:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        for name in names:
            info = connection.execute(f"PRAGMA table_info({name})").fetchall()
            columns = [row[1] for row in info]
            pk_columns = [row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])]
            order = ", ".join(f'"{column}"' for column in pk_columns) or "rowid"
            rows = []
            for row in connection.execute(f'SELECT rowid, * FROM "{name}" ORDER BY {order}'):
                rows.append({
                    "rowid": row[0],
                    "values": {column: _value(value) for column, value in zip(columns, row[1:])},
                })
            tables[name] = {
                "columns": columns,
                "primary_key": pk_columns,
                "row_count": len(rows),
                "rows": rows,
            }
    finally:
        connection.close()

    files = {}
    for path in sorted(item for item in data_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(data_dir).as_posix()
        if relative == "sentriface.db" or relative.startswith(("sentriface.db-", "logs/", "tmp/")):
            continue
        files[relative] = {
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    return {
        "contract": "sentriface.installation-state",
        "contract_version": 1,
        "data_dir": str(data_dir),
        "schema_version": user_version,
        "tables": tables,
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = capture(args.data_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Captured {len(payload['tables'])} tables and {len(payload['files'])} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
