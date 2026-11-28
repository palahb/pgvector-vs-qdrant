"""Write the config of the pgvector 4 GB rerun (G13): the six cells of E10 that did not finish, same job definitions and seeds, longer time limit.

Usage: python scripts/make_e10_4g_config.py [--time 48:00:00] [--out configs/examples/e10_hamsi_4g_rerun.json]
The experiment id stays E10_memory_limits so that the pilot gate of commit 0b0b905 still applies; the submission id tells the rerun apart.
"""
import argparse
import json
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "configs/examples/e10_memory_limits.json"


def build(time):
    cfg = json.loads(SRC.read_text())
    jobs = [j for j in cfg["stages"]["full"]["jobs"]
            if j["factors"]["limit"] == "4G" and j["factors"]["system"].startswith("pg_")]
    assert len(jobs) == 6, len(jobs)
    cfg["stages"] = {"pilot": cfg["stages"]["pilot"], "full": {"jobs": jobs}}  # pilot is kept for the loader and is not rendered
    cfg["resources"] = dict(cfg["resources"], time=time, array_concurrency=6)
    return cfg


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--time", default="48:00:00")
    ap.add_argument("--out", default="configs/examples/e10_hamsi_4g_rerun.json")
    a = ap.parse_args()
    Path(a.out).write_text(json.dumps(build(a.time), indent=2) + "\n")
    print("wrote", a.out)
