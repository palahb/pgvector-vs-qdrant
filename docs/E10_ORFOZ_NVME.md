# E10 on orfoz (NVMe), set 2 (G14): state on 28 November 2026

* Code: commit `0b0b905` (same checkout as the hamsi E10 set), so the only differences are the platform and the resources: partition `orfoz`, `-c 112`, `--mem=240G`, no hamsi exclude list.
  Configs written by `scripts/make_e10_orfoz_config.py`: `configs/examples/e10_orfoz_nvme_pilot.json` (3 tasks, 1.5 h) and `e10_orfoz_nvme_full.json` (36 tasks, 12 h, concurrency 3).
* Rendered on the cluster with `manage.py render` (submission ids `E10_memory_limits-orfoz-nvme-pilot` and `...-full`); `manage.py submit --dry-run` found the gate evidence (smoke of `0b0b905`, and for the full stage the E10 pilot).
* **Not submitted.** The first `manage.py submit` of both deployments ended with `sbatch ... returned non-zero exit status 1` and no job was created (the queue held only job 7085866, the hamsi 4G rerun). `sbatch --test-only` accepts the same
  script (estimated start 6 December 07:25), so the cause is not yet known. The error text of `sbatch` was not captured, and a direct `sbatch` call outside `manage.py` was refused by the permission layer, so the diagnosis is left to the author.
* Planned afterwards: the storage of every node a task ran on is checked with `bench/slurm/storage_check_part.sbatch --nodelist=<node>` (the 0b0b905 harness does not record the device of the work directory).
