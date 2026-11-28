"""Write the configs of the E10 NVMe set on the orfoz partition (G14): the full E10 matrix with the same job definitions, seeds and commit (0b0b905) as the hamsi set.

Only the resources change: partition orfoz, a whole 112-core node (the queue refuses fewer), 240 GB of its 256 GB, no hamsi exclude list.
Two files, because the time limit is per config: a pilot (canary for the 2 x 56 core layout) and the full matrix.
Usage: python scripts/make_e10_orfoz_config.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "configs/examples/e10_memory_limits.json"


def build(time):
    cfg = json.loads(SRC.read_text())
    res = {k: v for k, v in cfg["resources"].items() if k != "exclude"}
    res.update(partition="orfoz", cpus=112, memory="240G", time=time)
    cfg["resources"] = res
    return cfg


if __name__ == "__main__":
    for name, time, conc in (("pilot", "01:30:00", 3), ("full", "12:00:00", 3)):
        cfg = build(time)
        cfg["resources"]["array_concurrency"] = conc
        out = ROOT / f"configs/examples/e10_orfoz_nvme_{name}.json"
        out.write_text(json.dumps(cfg, indent=2) + "\n")
        print("wrote", out.relative_to(ROOT), cfg["resources"])
