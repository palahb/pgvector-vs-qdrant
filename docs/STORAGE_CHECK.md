# Storage of a compute node (checked 26 November 2026)

Job 7073390 (`bench/slurm/storage_check.sbatch`, read-only) on node hamsi120 of the `hamsi` partition, whole node as the partition requires.
The raw output is below, unedited.

## Reading

* The node has **one block device**, `sda` (1.1 TB, a MegaRAID MR9361-8i volume), with `rotational = 1`: spinning disks behind a RAID controller. `/` is
  `ext4` on `/dev/sda2`, and so is `/tmp` (`TMPDIR=/tmp`). The databases of every experiment lived there.
* **There is no NVMe device on this node** (`/dev/nvme*` does not exist, `nvme list` is not installed, no `nvme` entry in `/sys/block`).
* `/dev/shm` is a 93.5 GB `tmpfs` (RAM). It can hold the 1M x 1024 data (about 14 GB for pgvector with its TOAST data) but is memory,
  so it removes the disk from the question; it cannot stand in for an out-of-core test.
* `/arf/scratch` is Lustre (12.6 PB), shared and over the network; the code, images and results live there, the databases do not.

This is consistent with the disk probe of September (about 167 MB/s sequential, about 5 ms random read) and with the cold-start times of E10 (a pgvector cold
query of about one second at 1M).

## What this check does not cover (added 28 November)

It is **one node of one partition**. The cluster has other CPU partitions that were not looked at: `orfoz` (156 nodes, 112 cores, 256 GB), `barbun` (120 nodes, 40 cores, 384 GB), the
single large-memory node of `smp` (224 cores, 4 TB) and two GPU partitions. All CPU partitions carry the Slurm feature `weka` (a Weka file system), whose mount we did not find on the login
node. `TmpDisk` is 0 for every node, so Slurm does not describe node-local disks. The login node does have an NVMe device (`/dev/nvme0n1`), which is not where jobs run. The supervisor wrote that NVMe
could be used on TRUBA and in `/tmp`; **this check neither confirms nor refutes that for the other partitions.** The other `hamsi` nodes were not checked either, but the 8 nodes of E10 and the
September disk probe all behaved like a rotational disk (cold queries of 0.6 to 1.5 s).

## Update, 28 November: more nodes, and what TRUBA's documentation says

| Node | Partition | Job | `/tmp` | NVMe |
|---|---|---|---|---|
| hamsi120 | hamsi | 7073390 | `/dev/sda2`, ext4, rotational | none |
| hamsi124 | hamsi | 7084368 | `/dev/sda2`, ext4, rotational | none |
| orkinos1 | smp | 7084367 | `/dev/sda2`, ext4, rotational | none |
| orfoz183 | orfoz | 7084401 | `/dev/nvme0n1p3`, ext4 (root; `/tmp` is not a separate mount), Micron 7450, 894 GB, ROTA=0 | **yes** |
| akya7 | akya-cuda | 7084740 | `/dev/sdb2`, ext4, Intel SATA SSD 224 GB, ROTA=0 | none (SATA SSD) |
| barbun | barbun | 7084400 | pending at the time of writing | not yet checked |

Script: `bench/slurm/storage_check_part.sbatch`. On orkinos1 `/arf` is Lustre and no `weka` mount exists, so the `weka` feature in `sinfo` is not a node-local disk.

The queue page of the TRUBA user documentation
(https://docs.truba.gov.tr/1-kaynaklar/arf/arf_kuyruk_bilgisi.html, last updated 24 Dec 2025) says:
"Tüm sunucularda /tmp dizini NVMe disk olarak yapılandırılmıştır. Yüksek I/O gerektiren işlerinizde bu alanı kullanmanız önerilir. Özellikle akya-cuda sunucularında 1.4TB NVMe disk /tmp altında sunulmaktadır."
This is very likely the source of the supervisor's remark. **It contradicts what we measured on three nodes.** The same page lists hamsi as Xeon Gold 6338, while our hamsi nodes reported Xeon Gold 6258R, so the page may be out of date. The only concrete NVMe it names is on `akya-cuda`, a GPU partition that accepts GPU jobs only. The documentation is therefore right for `orfoz` and wrong for `hamsi` and `smp` as measured. On `akya7` the disks are SATA SSDs, not the 1.4 TB NVMe the page names. The `akya-cuda` check requested one GPU and used none; it was sent with the author's approval.
So the supervisor's remark holds for `orfoz` (112 cores per node, Xeon Platinum 8480+ per the documentation), which is a different CPU platform from `hamsi`. A pilot there is possible but would not be comparable with the `hamsi` results and would have to be reported as a separate platform.

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
