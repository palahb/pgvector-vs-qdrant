"""Paper figures from result.json files. Usage:
  python make_figures.py $BENCH_RESULTS paper/figures
Reads e1_scale/ (scale figures), e5_builds/ (build figure, falls back to e1) and e3_dims/ under the results root.
Color is the system (pgvector blue, Qdrant orange), line style is Qdrant's client path.
Rows whose recorded plan did not use the ANN index are left out of the curves.
"""
import glob
import json
import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PG, QD = "#2a78d6", "#eb6834"   # validated categorical slots 1 and 2
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
STYLE = {  # (label, color, linestyle, marker)
    "pg": ("pgvector", PG, "-", "o"),
    "grpc_raw": ("Qdrant, gRPC-lean", QD, "-", "s"),
    "grpc": ("Qdrant, gRPC client", QD, "--", "^"),
    "rest": ("Qdrant, REST client", QD, ":", "v"),
}

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8, "axes.labelsize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "lines.linewidth": 1.4,
    "lines.markersize": 4, "pdf.fonttype": 42, "savefig.bbox": "tight",
})


def load(root):
    """{n: {"pg": result, "qdrant": result}}, taking untagged runs only."""
    out = {}
    for path in glob.glob(os.path.join(root, "**", "result.json"), recursive=True):
        r = json.load(open(path))
        name = os.path.basename(os.path.dirname(path))
        if r.get("status") != "ok" or name not in ("pg", "qdrant"):
            continue
        out.setdefault(r["n"], {})[r["engine"]] = r
    return dict(sorted(out.items()))


def uses_index(row):
    plan = row.get("plan")
    return plan is None or all(p["uses_index"] for p in plan.values())


def sweep(result, proto, field):
    """Mean over reps per ef: [(ef, recall, value)] sorted by ef."""
    by_ef = {}
    for row in result["runs"][0]["latency"]:
        if row["proto"] == proto and uses_index(row) and row.get(field) is not None:
            by_ef.setdefault(row["ef"], []).append(row)
    return [(ef, sum(r["recall_at_k"] for r in rs) / len(rs), sum(r[field] for r in rs) / len(rs))
            for ef, rs in sorted(by_ef.items())]


def scale_label(n):
    return f"{n // 1_000_000}M" if n >= 1_000_000 else f"{n // 1000}K"


def fig_recall_latency(data, out):
    ns = list(data)
    fig, axes = plt.subplots(2, len(ns), figsize=(7.0, 4.4), sharey="row", squeeze=False)
    for j, n in enumerate(ns):
        top, bottom = axes[0][j], axes[1][j]
        for proto in ("pg", "grpc_raw", "grpc", "rest"):
            res = data[n].get("pg" if proto == "pg" else "qdrant")
            if not res:
                continue
            label, color, ls, mk = STYLE[proto]
            pts = sweep(res, proto, "mean_ms")
            top.plot([p[1] for p in pts], [p[2] for p in pts], ls=ls, marker=mk, color=color, label=label)
            if proto != "grpc":  # gRPC and gRPC-lean share the same engine time
                eng = sweep(res, proto, "server_mean_ms")
                lab = {"pg": "pgvector", "grpc_raw": "Qdrant, gRPC", "rest": "Qdrant, REST"}[proto]
                bottom.plot([p[1] for p in eng], [p[2] for p in eng], ls=ls, marker=mk, color=color, label=lab)
        top.set_title(f"{scale_label(n)} vectors", color=INK)
        for ax in (top, bottom):
            ax.set_yscale("log")
            ax.set_xlabel("Recall@10")
        if j == 0:
            top.set_ylabel("End-to-end latency, mean (ms)")
            bottom.set_ylabel("Engine-side time, mean (ms)")
    for row in axes:  # rows share y, so set readable ticks once every panel is drawn
        lo, hi = row[0].get_ylim()
        ticks = [t for t in (0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100) if lo <= t <= hi]
        row[0].set_yticks(ticks, [f"{t:g}" for t in ticks])
        row[0].minorticks_off()
        row[0].set_ylim(lo, hi)
    axes[0][0].legend(loc="upper left", frameon=False)
    axes[1][0].legend(loc="upper left", frameon=False)
    fig.tight_layout()
    save(fig, out, "recall_latency")


def fig_throughput(data, out):
    ns = list(data)
    fig, axes = plt.subplots(1, len(ns), figsize=(7.0, 2.6), sharey=True, squeeze=False)
    for j, n in enumerate(ns):
        ax = axes[0][j]
        notes = []
        for engine, protos in (("pg", ("pg",)), ("qdrant", ("grpc_raw", "grpc", "rest"))):
            res = data[n].get(engine)
            if not res or "conc_matched_ef" not in res["runs"][0]:
                continue
            ef = res["runs"][0]["conc_matched_ef"]
            lat_rows = [r for r in res["runs"][0]["latency"] if r["ef"] == ef]
            if not all(uses_index(r) for r in lat_rows):
                continue  # concurrency at this ef ran on a non-index plan
            rows = [r for r in res["runs"][0]["concurrency"] if r["ef"] == ef]
            if rows:
                notes.append(f"{'pgvector' if engine == 'pg' else 'Qdrant'} ef={ef}, R={rows[0]['recall_at_k']:.3f}")
            for proto in protos:
                pts = sorted((r["clients"], r["throughput_qps"]) for r in rows if r["proto"] == proto)
                label, color, ls, mk = STYLE[proto]
                ax.plot([p[0] for p in pts], [p[1] for p in pts], ls=ls, marker=mk, color=color, label=label)
        clients = sorted({r["clients"] for e in data[n].values() for r in e["runs"][0].get("concurrency", [])})
        ax.set_xscale("log", base=2)
        ax.set_xticks(clients, [str(c) for c in clients])
        ax.minorticks_off()
        ax.set_xlabel("Concurrent clients")
        ax.set_title(f"{scale_label(n)} vectors", color=INK, pad=22)
        ax.text(0.5, 1.02, "\n".join(notes), transform=ax.transAxes, ha="center", va="bottom",
                fontsize=6.5, color=MUTED)
        if j == 0:
            ax.set_ylabel("Throughput (queries/s)")
    axes[0][0].legend(loc="upper left", frameon=False)
    fig.tight_layout()
    save(fig, out, "throughput")


def e5_builds(root):
    """{n: {"pg": build, "qdrant": build}} with each phase averaged over the repeated builds on one node."""
    out = {}
    for d in glob.glob(os.path.join(root, "e5_builds", "n*")):
        for eng in ("pg", "qdrant"):
            bs = [r["build"] for r in (json.load(open(p)) for p in glob.glob(os.path.join(d, f"{eng}_r*", "result.json")))
                  if r.get("status") == "ok"]
            if bs:
                out.setdefault(int(os.path.basename(d)[1:]), {})[eng] = {
                    k: sum(b[k] for b in bs) / len(bs) for k in bs[0] if isinstance(bs[0][k], (int, float))}
    return dict(sorted(out.items()))


def fig_build(builds, out):
    """builds: {n: {"pg": build, "qdrant": build}}"""
    ns = list(builds)
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    width = 0.36
    for i, n in enumerate(ns):
        pg, qd = builds[n].get("pg"), builds[n].get("qdrant")
        if pg:
            b = pg
            ax.bar(i - width / 2 - 0.01, b["load_s"], width, color=PG, alpha=0.45, edgecolor="white", linewidth=1,
                   label="pgvector load (COPY)" if i == 0 else None)
            ax.bar(i - width / 2 - 0.01, b["index_s"], width, bottom=b["load_s"], color=PG, edgecolor="white",
                   linewidth=1, label="pgvector CREATE INDEX" if i == 0 else None)
        if qd:
            b = qd
            ax.bar(i + width / 2 + 0.01, b["upload_s"], width, color=QD, alpha=0.45, edgecolor="white", linewidth=1,
                   label="Qdrant upload" if i == 0 else None)
            ax.bar(i + width / 2 + 0.01, b["index_wait_s"], width, bottom=b["upload_s"], color=QD, edgecolor="white",
                   linewidth=1, label="Qdrant indexing after upload" if i == 0 else None)
    ax.set_xticks(range(len(ns)), [scale_label(n) for n in ns])
    ax.set_ylabel("Build time (s)")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout()
    save(fig, out, "build_time")


def fig_dims(root, out, ef=64):
    """Engine time and recall against dimension: pgvector, Qdrant default, Qdrant forced indexing."""
    rows = {}
    for path in glob.glob(os.path.join(root, "*", "*", "result.json")):
        r = json.load(open(path))
        if r.get("status") != "ok":
            continue
        name = os.path.basename(os.path.dirname(path))
        proto = "pg" if r["engine"] == "pg" else "grpc_raw"
        pts = {e: (rec, eng) for e, rec, eng in sweep(r, proto, "server_mean_ms")}
        if ef in pts:
            st = r["build"].get("final_state", {})
            unindexed = (st["points"] - st["indexed"]) / st["points"] if st else 0.0
            rows.setdefault(name, []).append((r["dim"], pts[ef][1], pts[ef][0], unindexed))
    if not rows:
        return
    series = [("pg", "pgvector", PG, "-", "o"), ("qdrant_forced", "Qdrant, every segment indexed", QD, "-", "s"),
              ("qdrant_default", "Qdrant, default indexing threshold", QD, "--", "^")]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.0, 2.5))
    for key, label, color, ls, mk in series:
        pts = sorted(rows.get(key, []))
        if not pts:
            continue
        a.plot([p[0] for p in pts], [p[1] for p in pts], ls=ls, marker=mk, color=color, label=label)
        b.plot([p[0] for p in pts], [p[2] for p in pts], ls=ls, marker=mk, color=color, label=label)
        if key == "qdrant_default":
            for d, eng, _, un in pts:
                if un > 0:
                    a.annotate(f"{un:.1%}", (d, eng), textcoords="offset points", xytext=(0, 6),
                               ha="center", fontsize=6, color=MUTED)
    dims = sorted({p[0] for v in rows.values() for p in v})
    for ax in (a, b):
        ax.set_xticks(dims, [str(d) for d in dims])
        ax.set_xlabel("Dimensions (Matryoshka truncation)")
    a.set_ylabel(f"Engine-side time at ef={ef} (ms)")
    b.set_ylabel(f"Recall@10 at ef={ef}")
    a.set_ylim(bottom=0)
    handles, labels = a.get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout()
    save(fig, out, "dimensionality")


def save(fig, out, name):
    os.makedirs(out, exist_ok=True)
    fig.savefig(os.path.join(out, f"{name}.pdf"))
    fig.savefig(os.path.join(out, f"{name}.png"), dpi=160)
    plt.close(fig)
    print("wrote", os.path.join(out, name + ".pdf"))


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    out = sys.argv[2] if len(sys.argv) > 2 else "figures"
    data = load(os.path.join(root, "e1_scale"))
    if data:
        fig_recall_latency(data, out)
        fig_throughput(data, out)
    builds = e5_builds(root) or {n: {e: r["build"] for e, r in d.items()} for n, d in data.items()}
    if builds:
        fig_build(builds, out)
    fig_dims(os.path.join(root, "e3_dims"), out)
