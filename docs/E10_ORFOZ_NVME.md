# E10 on orfoz (NVMe), set 2 (G14): state on 28 November 2026

* Code: commit `0b0b905` (same checkout as the hamsi E10 set), so the only differences are the platform and the resources: partition `orfoz`, `-c 112`, `--mem=230G`, no hamsi exclude list.
  Configs written by `scripts/make_e10_orfoz_config.py`: `configs/examples/e10_orfoz_nvme_pilot.json` (3 tasks, 1.5 h) and `e10_orfoz_nvme_full.json` (36 tasks, 12 h, concurrency 3).
* Rendered on the cluster with `manage.py render` (submission ids `E10_memory_limits-orfoz-nvme-pilot` and `...-full`); `manage.py submit --dry-run` found the gate evidence (smoke of `0b0b905`, and for the full stage the E10 pilot).
* **Submitted, 28 November.** The first attempt (`--mem=240G`) failed with `sbatch: error: CPU count per node can not be satisfied`: the orfoz queue caps memory at `MaxMemPerCPU=2170` MB, 237 GB for 112 CPUs, and 240 GB asks for 114 CPUs.
  (`manage.py` hides the `sbatch` message inside the exception; it was read from the exception's `stderr`. `sbatch --test-only` had accepted the same script.) With `--mem=230G`: pilot job `7086040` (3 tasks, 1.5 h) and full job `7086042`
  (36 tasks, 12 h, concurrency 3), both pending, estimated first start 6 December. The pilot runs as a canary for the 2 x 56 core layout; the full array does not wait for it. If the pilot shows a problem, the full array is cancelled before it starts.
  The gate evidence is the smoke of `0b0b905` and the E10 pilot of `0b0b905` (hamsi); the orfoz pilot is not a gate here.
* The node is 2 sockets x 56 cores, SMT off, 256 GB (`scontrol show node orfoz211`), so `pick_cores` (server on 8 cores of the first NUMA node, client on the other) needs no change; the client gets 56 cores instead of 28.
* Planned afterwards: the storage of every node a task ran on is checked with `bench/slurm/storage_check_part.sbatch --nodelist=<node>` (the 0b0b905 harness does not record the device of the work directory).
