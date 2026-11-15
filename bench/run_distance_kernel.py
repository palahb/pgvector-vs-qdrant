#!/usr/bin/env python3
"""Compile and run the deterministic cosine-dot lower-bound probe on one pinned core."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def command_output(command: list[str]) -> str:
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout


def cpu_flags() -> list[str]:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith(("flags", "Features")):
                return sorted(line.split(":", 1)[1].split())
    except OSError:
        pass
    return []


def parse_json_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vectors", type=int, default=16384)
    parser.add_argument("--dim", type=int, default=1024)
    parser.add_argument("--passes", type=int, default=12)
    parser.add_argument("--core", type=int, default=0)
    parser.add_argument("--compiler", default=os.environ.get("CC", "cc"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.vectors, args.dim, args.passes) <= 0 or args.core < 0:
        parser.error("vectors, dim and passes must be positive; core must be non-negative")

    with tempfile.TemporaryDirectory(prefix="distance-kernel-") as tmp:
        binary = Path(tmp) / "distance_kernel"
        compile_command = [
            args.compiler, "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror",
            str(ROOT / "distance_kernel.c"), "-lm", "-o", str(binary),
        ]
        command_output(compile_command)
        run_command = [str(binary), "--vectors", str(args.vectors), "--dim", str(args.dim), "--passes", str(args.passes)]
        if platform.system() == "Linux":
            run_command = ["taskset", "-c", str(args.core), *run_command]
        kernels = parse_json_lines(command_output(run_command))

    checksums = [item["checksum"] for item in kernels]
    scale = max(abs(checksums[0]), 1.0) if checksums else 1.0
    checksum_relative_spread = (max(checksums) - min(checksums)) / scale if checksums else None
    report = {
        "schema_version": 1,
        "probe": (
            "dot-product stage used by cosine distance after vector normalization; generated values are not "
            "normalized because the arithmetic path is identical; excludes graph traversal and database overhead"
        ),
        "host": platform.node(),
        "machine": platform.machine(),
        "compiler": command_output([args.compiler, "--version"]).splitlines()[0],
        "compile_command": compile_command[:-1] + ["OUTPUT"],
        "cpu_flags": cpu_flags(),
        "core": args.core,
        "kernels": kernels,
        "checksum_relative_spread": checksum_relative_spread,
        "checksum_consistent": checksum_relative_spread is not None and checksum_relative_spread < 1e-4,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"kernels={len(kernels)} checksum_consistent={report['checksum_consistent']} output={args.output}")
    return 0 if report["checksum_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
