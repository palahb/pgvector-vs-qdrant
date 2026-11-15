#!/usr/bin/env python3
"""Create lossless schema-v2 JSONL views of legacy benchmark results.

Unknown provenance is represented explicitly as null and `legacy_incomplete`; it is
never guessed. Original result files and raw arrays are not modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(value: Any, prefix: str) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


def adapt_result(result: dict[str, Any], source_path: str, source_sha256: str) -> dict[str, Any]:
    """Return a copy with v2 identity fields; preserve every legacy key and value."""
    adapted = dict(result)
    adapted.update(
        {
            "schema_version": 2,
            "provenance_status": "legacy_incomplete",
            "experiment_id": stable_id(
                {"source_path": source_path, "source_sha256": source_sha256}, "legacy"
            ),
            "config_id": stable_id(result.get("args", {}), "cfg"),
            "seed": result.get("seed"),
            "warm_seed": result.get("warm_seed"),
            "code_commit": result.get("code_commit"),
            "code_dirty": result.get("code_dirty"),
            "command": result.get("command"),
            "legacy_source": {
                "path": source_path,
                "sha256": source_sha256,
                "missing_provenance": [
                    key
                    for key in ("seed", "warm_seed", "code_commit", "code_dirty", "command")
                    if result.get(key) is None
                ],
            },
        }
    )
    return adapted


def adapt_tree(root: Path) -> Iterable[dict[str, Any]]:
    root = root.resolve()
    for path in sorted(root.glob("**/result.json")):
        source = path.relative_to(root).as_posix()
        result = json.loads(path.read_text())
        yield adapt_result(result, source, sha256_file(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Legacy results root")
    parser.add_argument("--output", type=Path, required=True, help="Destination JSONL file")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    count = 0
    with temporary.open("w") as stream:
        for result in adapt_tree(args.root):
            stream.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
            count += 1
    temporary.replace(args.output)
    print(f"adapted={count} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
