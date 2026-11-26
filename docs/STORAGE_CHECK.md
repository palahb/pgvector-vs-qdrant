# Storage of a compute node (checked 26 November 2026)

Job 7073390 (`bench/slurm/storage_check.sbatch`, read-only) on node hamsi120 of the `hamsi` partition, whole node as the partition requires.
The raw output is below, unedited.

## Reading

* The node has **one block device**, `sda` (1.1 TB, a MegaRAID MR9361-8i volume), with `rotational = 1`: spinning disks behind a RAID controller. `/` is
  `ext4` on `/dev/sda2`, and so is `/tmp` (`TMPDIR=/tmp`). The databases of every experiment lived there.
* **There is no NVMe device** (`/dev/nvme*` does not exist, `nvme list` is not installed, no `nvme` entry in `/sys/block`).
* `/dev/shm` is a 93.5 GB `tmpfs` (RAM). It can hold the 1M x 1024 data (about 14 GB for pgvector with its TOAST data) but is memory,
  so it removes the disk from the question; it cannot stand in for an out-of-core test.
* `/arf/scratch` is Lustre (12.6 PB), shared and over the network; the code, images and results live there, the databases do not.

This is consistent with the disk probe of September (about 167 MB/s sequential, about 5 ms random read) and with the cold-start times of E10 (a pgvector cold
query of about one second at 1M).

## Consequence for the paper

The paper keeps the label "HDD, worst case" for every result that depends on storage (memory limits, cold starts, build I/O). The NVMe repetition the referee
asked for (M4, M5) cannot be done on this cluster: there is nothing to run it on. The single-configuration pilot that the plan named as a stretch is therefore
**not possible**; a `tmpfs` build arm would only measure the build without a disk, which E9's `UNLOGGED` arms already approximate, and is not run.

## Raw output

```
node=hamsi120 job=7073390 date=2026-11-26T20:33:03Z
TMPDIR=/tmp
== lsblk
NAME    SIZE TYPE ROTA TRAN MODEL     FSTYPE MOUNTPOINT
sda     1.1T disk    1      MR9361-8i        
|-sda1    4G part    1                swap   [SWAP]
`-sda2  1.1T part    1                ext4   /
== rotational flag per block device
sda rotational=1
== findmnt for the paths the benchmark uses
TARGET SOURCE    FSTYPE  SIZE AVAIL
/      /dev/sda2 ext4    1.1T    1T
TARGET SOURCE    FSTYPE  SIZE AVAIL
/      /dev/sda2 ext4    1.1T    1T
TARGET   SOURCE FSTYPE  SIZE AVAIL
/dev/shm tmpfs  tmpfs  93.5G 93.1G
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.2P
== df
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda2       1.1T   11G  1.1T   2% /
/dev/sda2       1.1T   11G  1.1T   2% /
tmpfs            94G  448M   94G   1% /dev/shm
== nvme
nvme tool not available
ls: cannot access '/dev/nvme*': No such file or directory
== mounts of interest
tmpfs /dev/shm tmpfs rw,nosuid,nodev,inode64 0 0
== /sys/block summary
sda
STORAGE_CHECK_DONE
```
