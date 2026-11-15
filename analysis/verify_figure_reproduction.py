#!/usr/bin/env python3
"""Regenerate paper figures and compare image pixels/PDF renders with tracked files."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops


FIGURES = ("build_time", "recall_latency", "throughput", "dimensionality")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixel_equal(first: Path, second: Path) -> bool:
    left = Image.open(first).convert("RGBA")
    right = Image.open(second).convert("RGBA")
    return left.size == right.size and ImageChops.difference(left, right).getbbox() is None


def render_pdf(pdf: Path, target: Path) -> None:
    subprocess.run(
        ["pdftoppm", "-png", "-r", "150", "-singlefile", str(pdf), str(target)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def verify(results: Path, expected: Path) -> dict:
    repo = Path(__file__).resolve().parents[1]
    generator = repo / "bench/make_figures.py"
    with tempfile.TemporaryDirectory(prefix="pgvector-figures-") as directory:
        generated = Path(directory) / "generated"
        generated.mkdir()
        subprocess.run([sys.executable, str(generator), str(results), str(generated)], check=True)
        rows = {}
        for name in FIGURES:
            old_png, new_png = expected / f"{name}.png", generated / f"{name}.png"
            old_pdf, new_pdf = expected / f"{name}.pdf", generated / f"{name}.pdf"
            row = {
                "tracked_png_sha256": sha256_file(old_png),
                "generated_png_sha256": sha256_file(new_png),
                "png_pixels_equal": pixel_equal(old_png, new_png),
                "tracked_pdf_sha256": sha256_file(old_pdf),
                "generated_pdf_sha256": sha256_file(new_pdf),
                "pdf_bytes_equal": old_pdf.read_bytes() == new_pdf.read_bytes(),
                "pdf_render_equal": None,
            }
            if shutil.which("pdftoppm"):
                old_render = Path(directory) / f"{name}_tracked"
                new_render = Path(directory) / f"{name}_generated"
                render_pdf(old_pdf, old_render)
                render_pdf(new_pdf, new_render)
                row["pdf_render_equal"] = pixel_equal(
                    old_render.with_suffix(".png"), new_render.with_suffix(".png")
                )
            rows[name] = row
    success = all(
        row["png_pixels_equal"] and row["pdf_render_equal"] is not False
        for row in rows.values()
    )
    return {
        "schema_version": 1,
        "verdict": "reproduced" if success else "mismatch",
        "results_root": results.as_posix(),
        "tracked_figure_root": expected.as_posix(),
        "generator": "bench/make_figures.py",
        "generator_sha256": sha256_file(generator),
        "comparison": "PNG RGBA pixels and PDF renders at 150 DPI; byte hashes retained for provenance",
        "figures": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("expected", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.results, args.expected)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"verdict={report['verdict']} figures={len(report['figures'])}")
    return 0 if report["verdict"] == "reproduced" else 1


if __name__ == "__main__":
    raise SystemExit(main())
