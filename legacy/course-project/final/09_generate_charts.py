import json
import matplotlib.pyplot as plt
import numpy as np
import os

os.makedirs("charts", exist_ok=True)

# ── CHART 1: Recall-Latency curves across all scales ─────────
print("Chart 1: Recall-latency curves...")

scales = ["100K", "500K", "1M"]
files = ["results_100K.json", "results_500K.json", "results_1M.json"]

# Try to load 100K from milestone if scale file doesn't exist
if not os.path.exists("results_100K.json"):
    # Use milestone results
    with open("benchmark_results.json") as f:
        milestone = json.load(f)
    with open("build_times.json") as f:
        bt = json.load(f)
    results_100k = {
        "scale": 100000,
        "build_times": {
            "pgvector_total_s": bt["pgvector_total_build_time_s"],
            "qdrant_total_s": bt["qdrant_total_build_time_s"],
        },
        "benchmarks": milestone,
    }
    with open("results_100K.json", "w") as f:
        json.dump(results_100k, f, indent=2)

fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), sharey=True)
for ax, scale, fname in zip(axes, scales, files):
    if not os.path.exists(fname):
        ax.text(0.5, 0.5, f"{scale}\n(not run)", ha='center', va='center',
                transform=ax.transAxes, fontsize=14, color='gray')
        ax.set_title(f"Scale: {scale}")
        continue
    with open(fname) as f:
        data = json.load(f)
    benchmarks = data["benchmarks"]

    pgv = [b for b in benchmarks if b["system"] == "pgvector"]
    qdr = [b for b in benchmarks if b["system"] == "qdrant"]

    pgv_lat = [b["mean_latency_ms"] for b in pgv]
    pgv_rec = [b["recall_at_10"] for b in pgv]
    qdr_lat = [b["mean_latency_ms"] for b in qdr]
    qdr_rec = [b["recall_at_10"] for b in qdr]

    ax.plot(pgv_lat, pgv_rec, "o-", label="pgvector", color="tab:blue", markersize=8)
    ax.plot(qdr_lat, qdr_rec, "s-", label="Qdrant", color="tab:red", markersize=8)

    for b in pgv:
        ax.annotate(f"ef={b['ef']}", (b["mean_latency_ms"], b["recall_at_10"]),
                    fontsize=8, xytext=(5, -10), textcoords="offset points", color="tab:blue")
    for b in qdr:
        ax.annotate(f"ef={b['ef']}", (b["mean_latency_ms"], b["recall_at_10"]),
                    fontsize=8, xytext=(5, 5), textcoords="offset points", color="tab:red")

    ax.set_xlabel("Mean Latency (ms)")
    ax.set_title(f"Scale: {scale}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")

axes[0].set_ylabel("Recall@10")
fig.suptitle("Recall–Latency Tradeoff Across Dataset Scales", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig("charts/recall_latency_scales.png", dpi=150, bbox_inches="tight")
print("  saved charts/recall_latency_scales.png")
plt.close()

# ── CHART 2: Build time across scales ────────────────────────
print("Chart 2: Build time scaling...")

scales_x = []
pgv_build = []
qdr_build = []

for scale, fname in zip([100_000, 500_000, 1_000_000], files):
    if not os.path.exists(fname):
        continue
    with open(fname) as f:
        data = json.load(f)
    scales_x.append(scale)
    pgv_build.append(data["build_times"]["pgvector_total_s"])
    qdr_build.append(data["build_times"]["qdrant_total_s"])

if scales_x:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    width = 0.35
    x = np.arange(len(scales_x))
    ax.bar(x - width/2, pgv_build, width, label="pgvector", color="tab:blue")
    ax.bar(x + width/2, qdr_build, width, label="Qdrant", color="tab:red")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s//1000}K" if s < 1_000_000 else "1M" for s in scales_x])
    ax.set_xlabel("Dataset Size")
    ax.set_ylabel("Total Build Time (seconds)")
    ax.set_title("Index Build Time vs. Dataset Size")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)

    for i, (p, q) in enumerate(zip(pgv_build, qdr_build)):
        ax.text(i - width/2, p + max(pgv_build)*0.01, f"{p:.0f}s",
                ha="center", fontsize=9)
        ax.text(i + width/2, q + max(pgv_build)*0.01, f"{q:.0f}s",
                ha="center", fontsize=9)

    plt.tight_layout()
    plt.savefig("charts/build_time_scaling.png", dpi=150, bbox_inches="tight")
    print("  saved charts/build_time_scaling.png")
    plt.close()

# ── CHART 3: Concurrency — throughput and latency ────────────
print("Chart 3: Concurrency behavior...")

if os.path.exists("results_concurrency.json"):
    with open("results_concurrency.json") as f:
        conc = json.load(f)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    Cs = sorted(set(r["concurrency"] for r in conc))
    for sys, color, marker in [("pgvector", "tab:blue", "o"), ("qdrant", "tab:red", "s")]:
        rows = [r for r in conc if r["system"] == sys]
        rows.sort(key=lambda r: r["concurrency"])
        xs = [r["concurrency"] for r in rows]
        thrs = [r["throughput_qps"] for r in rows]
        mlats = [r["mean_latency_ms"] for r in rows]
        p99s = [r["p99_latency_ms"] for r in rows]

        ax1.plot(xs, thrs, marker=marker, color=color, label=sys,
                 markersize=10, linewidth=2)
        ax2.plot(xs, mlats, marker=marker, color=color, label=f"{sys} (mean)",
                 markersize=10, linewidth=2)
        ax2.plot(xs, p99s, marker=marker, color=color, label=f"{sys} (p99)",
                 markersize=10, linewidth=2, linestyle="--", alpha=0.5)

    ax1.set_xlabel("Concurrent Clients")
    ax1.set_ylabel("Throughput (queries/sec)")
    ax1.set_title("Throughput vs. Concurrency")
    ax1.set_xticks(Cs)
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.set_xlabel("Concurrent Clients")
    ax2.set_ylabel("Latency (ms)")
    ax2.set_title("Latency vs. Concurrency")
    ax2.set_xticks(Cs)
    ax2.grid(True, alpha=0.3)
    ax2.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig("charts/concurrency.png", dpi=150, bbox_inches="tight")
    print("  saved charts/concurrency.png")
    plt.close()

# ── CHART 4: Dimensionality sensitivity ──────────────────────
print("Chart 4: Dimensionality sensitivity...")

if os.path.exists("results_dimensionality.json"):
    with open("results_dimensionality.json") as f:
        dim = json.load(f)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

    for sys, color, marker in [("pgvector", "tab:blue", "o"), ("qdrant", "tab:red", "s")]:
        rows = [r for r in dim if r["system"] == sys]
        rows.sort(key=lambda r: r["dimensions"])
        xs = [r["dimensions"] for r in rows]
        lats = [r["mean_latency_ms"] for r in rows]
        recs = [r["recall_at_10"] for r in rows]

        ax1.plot(xs, lats, marker=marker, color=color, label=sys,
                 markersize=10, linewidth=2)
        ax2.plot(xs, recs, marker=marker, color=color, label=sys,
                 markersize=10, linewidth=2)

    ax1.set_xlabel("Embedding Dimensions")
    ax1.set_ylabel("Mean Latency (ms)")
    ax1.set_title("Latency vs. Dimensionality")
    ax1.grid(True, alpha=0.3)
    ax1.legend()

    ax2.set_xlabel("Embedding Dimensions")
    ax2.set_ylabel("Recall@10")
    ax2.set_title("Recall vs. Dimensionality")
    ax2.grid(True, alpha=0.3)
    ax2.legend()

    plt.tight_layout()
    plt.savefig("charts/dimensionality.png", dpi=150, bbox_inches="tight")
    print("  saved charts/dimensionality.png")
    plt.close()

print("\nAll charts generated in charts/ directory")