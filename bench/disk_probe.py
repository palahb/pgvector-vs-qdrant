"""Measures the node-local disk the databases live on: sequential write and 4 KiB / 8 KiB
random reads with O_DIRECT, so the page cache is bypassed. Decides how E4 (memory pressure)
results can be read: an SSD serves random 8 KiB reads in ~0.1 ms, a spinning disk in ~5-10 ms.
Usage: python disk_probe.py [dir] [size_gb]
"""
import json
import mmap
import os
import random
import statistics as st
import sys
import time


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TMPDIR", "/tmp")
    size = int(float(sys.argv[2]) if len(sys.argv) > 2 else 16) * 2**30
    path = os.path.join(d, f"disk_probe_{os.getpid()}.bin")
    block = 64 * 2**20
    buf = os.urandom(block)
    t0 = time.perf_counter()
    with open(path, "wb") as f:
        for _ in range(size // block):
            f.write(buf)
        f.flush()
        os.fsync(f.fileno())
    write_s = time.perf_counter() - t0
    out = {"dir": d, "size_gb": size / 2**30, "seq_write_mb_s": round(size / 2**20 / write_s, 1)}

    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECT", 0))
    try:
        for io in (4096, 8192):
            aligned = mmap.mmap(-1, io)  # page-aligned buffer, required by O_DIRECT
            lat = []
            deadline = time.perf_counter() + 20
            while time.perf_counter() < deadline and len(lat) < 20000:
                off = random.randrange(0, size // io) * io
                t = time.perf_counter_ns()
                os.preadv(fd, [aligned], off)
                lat.append((time.perf_counter_ns() - t) / 1e6)
            lat.sort()
            out[f"rand_{io // 1024}k"] = {"reads": len(lat), "mean_ms": round(st.mean(lat), 4),
                                          "p50_ms": round(lat[len(lat) // 2], 4),
                                          "p99_ms": round(lat[int(len(lat) * 0.99)], 4),
                                          "iops_qd1": round(1000 / st.mean(lat))}
    except OSError as e:
        out["error"] = f"O_DIRECT read failed: {e}"
    finally:
        os.close(fd)
        os.remove(path)
    rot = {}
    for dev in os.listdir("/sys/block"):
        p = f"/sys/block/{dev}/queue/rotational"
        if os.path.exists(p):
            rot[dev] = open(p).read().strip()
    out["rotational_flags"] = rot
    verdict = out.get("rand_8k", {}).get("p50_ms")
    out["verdict"] = None if verdict is None else ("ssd-like" if verdict < 1 else "spinning-disk-like")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
