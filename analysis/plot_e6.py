#!/usr/bin/env python3
"""Render the E6 pilot segment/thread latency, CPU and throughput figure."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


PG, QD1, QDA = "#2a78d6", "#eb6834", "#8f3fbc"
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.edgecolor": MUTED,
    "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 1.4,
    "lines.markersize": 4, "pdf.fonttype": 42, "savefig.bbox": "tight",
})


def error(metric):
    mean = metric["mean"]
    low, high = metric.get("ci95_low"), metric.get("ci95_high")
    return mean, None if low is None else [[mean - low], [high - mean]]


def qdrant_series(rows, metric_name, threads):
    chosen = sorted(
        (row for row in rows if row["engine"] == "qdrant" and row["search_threads"] == threads),
        key=lambda row: int(row["segments"]),
    )
    x, y, lo, hi = [], [], [], []
    for row in chosen:
        metric = row["metrics"][metric_name]
        x.append(int(row["segments"]))
        y.append(metric["mean"])
        lo.append(metric["mean"] - metric["ci95_low"])
        hi.append(metric["ci95_high"] - metric["mean"])
    return x, y, [lo, hi]


def plot(report: dict, output_stem: Path, target: float = 0.95) -> None:
    latency = [row for row in report["matched_recall_aggregates"] if row["recall_target"] == target]
    concurrency = [
        row for row in report["matched_concurrency_aggregates"]
        if row["recall_target"] == target and row["clients"] == 32
    ]
    pg_latency = next(row for row in latency if row["engine"] == "pg")
    pg_concurrency = next(row for row in concurrency if row["engine"] == "pg")

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.35))
    panels = [
        (axes[0], latency, "mean_ms", pg_latency, "Mean latency (ms)", "a  Single-client latency"),
        (axes[1], latency, "server_cpu_ms_per_query", pg_latency, "Server CPU (ms/query)", "b  CPU efficiency"),
        (axes[2], concurrency, "throughput_qps", pg_concurrency, "Throughput at C=32 (QPS)", "c  Closed-loop throughput"),
    ]
    for axis, rows, metric_name, pg_row, ylabel, title in panels:
        for threads, color, linestyle, marker, label in (
            (1, QD1, "--", "s", "Qdrant, 1 search thread"),
            ("auto", QDA, "-", "o", "Qdrant, auto threads"),
        ):
            x, y, yerr = qdrant_series(rows, metric_name, threads)
            axis.errorbar(x, y, yerr=yerr, color=color, linestyle=linestyle, marker=marker,
                          capsize=2, label=label)
        pg_metric = pg_row["metrics"][metric_name]
        axis.axhline(pg_metric["mean"], color=PG, linewidth=1.4, label="pgvector, one graph")
        if pg_metric.get("ci95_low") is not None:
            axis.axhspan(pg_metric["ci95_low"], pg_metric["ci95_high"], color=PG, alpha=0.12)
        axis.set(xlabel="Qdrant segment target", ylabel=ylabel, title=title, xticks=[1, 2, 4, 8])
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.08))
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_stem.with_suffix(".pdf"))
    fig.savefig(output_stem.with_suffix(".png"), dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output_stem", type=Path)
    parser.add_argument("--target", type=float, default=0.95)
    args = parser.parse_args()
    plot(json.loads(args.analysis.read_text()), args.output_stem, args.target)
    print(f"wrote {args.output_stem.with_suffix('.pdf')} and {args.output_stem.with_suffix('.png')}")


if __name__ == "__main__":
    main()
