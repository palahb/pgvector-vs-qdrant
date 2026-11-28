# Storage of a compute node (checked 26 November 2026)

Job 7073390 (`bench/slurm/storage_check.sbatch`, read-only) on node hamsi120 of the `hamsi` partition, whole node as the partition requires.
The raw output is below, unedited.

## Reading

* The node has **one block device**, `sda` (1.1 TB, a MegaRAID MR9361-8i volume), with `rotational = 1`: spinning disks behind a RAID controller. `/` is
  `ext4` on `/dev/sda2`, and so is `/tmp` (`TMPDIR=/tmp`). The databases of every experiment lived there.
* **There is no NVMe device on this node** (this section is hamsi120 only; see the table below for the others) (`/dev/nvme*` does not exist, `nvme list` is not installed, no `nvme` entry in `/sys/block`).
* `/dev/shm` is a 93.5 GB `tmpfs` (RAM). It can hold the 1M x 1024 data (about 14 GB for pgvector with its TOAST data) but is memory,
  so it removes the disk from the question; it cannot stand in for an out-of-core test.
* `/arf/scratch` is Lustre (12.6 PB), shared and over the network; the code, images and results live there, the databases do not.

This is consistent with the disk probe of September (about 167 MB/s sequential, about 5 ms random read) and with the cold-start times of E10 (a pgvector cold
query of about one second at 1M).

## All nodes checked (26 and 28 November)

| Node | Partition | Job | `/tmp` | NVMe |
|---|---|---|---|---|
| hamsi120 | hamsi | 7073390 | `/dev/sda2`, ext4, rotational (MR9361-8i RAID volume) | none |
| hamsi124 | hamsi | 7084368 | `/dev/sda2`, ext4, rotational (MR9361-8i) | none |
| barbun16 | barbun | 7084400 | `/dev/sda2`, ext4, rotational (PERC H730P) | none |
| orkinos1 | smp | 7084367 | `/dev/sda2`, ext4, rotational (MR9363-4i) | none |
| akya7 | akya-cuda | 7084740 | `/dev/sdb2`, ext4, Intel SATA SSD 224 GB, ROTA=0 | none (SATA SSD) |
| **orfoz183** | **orfoz** | 7084401 | `/dev/nvme0n1p3`, ext4 (root; `/tmp` is not a separate mount), Micron 7450, 894 GB, ROTA=0 | **yes** |

Scripts: `bench/slurm/storage_check.sbatch` (hamsi120) and `bench/slurm/storage_check_part.sbatch` (the others). One node per partition except `hamsi`, so the
statements below are about these nodes, not about every node of a partition. Raw outputs are at the end. The login node also has an NVMe device (`/dev/nvme0n1`); jobs do not run there.

The queue page of the TRUBA user documentation (https://docs.truba.gov.tr/1-kaynaklar/arf/arf_kuyruk_bilgisi.html, last updated 24 Dec 2025) says:
"Tüm sunucularda /tmp dizini NVMe disk olarak yapılandırılmıştır. Yüksek I/O gerektiren işlerinizde bu alanı kullanmanız önerilir. Özellikle akya-cuda sunucularında 1.4TB NVMe disk /tmp altında sunulmaktadır."
This is very likely the source of the supervisor's remark (17 November: "TRUBA'da NVMe kullanabilirsin /tmp de"). It holds on orfoz183 and **does not hold** on the hamsi, barbun, smp and akya7 nodes
above; on akya7 the disks are 224 GB SATA SSDs, not a 1.4 TB NVMe. The `akya-cuda` check requested one GPU and used none (sent with the author's approval). The same page lists hamsi as Xeon Gold 6338,
while our measurements (`docs/BUILD_INFO.md`) report Xeon Gold 6258R, so the page may be out of date. The `weka` Slurm feature on the CPU partitions is not a node-local disk: no `weka` mount exists on the nodes checked, `/arf` is Lustre.

The September disk probe (about 167 MB/s sequential, about 4.8 ms random read) and the cold-start times of E10 (a pgvector cold query of 0.6 to 1.5 s) are consistent with the rotational disks of hamsi.

## Consequence for the paper

Every result that depends on storage (memory limits, cold starts, build I/O) was measured on a rotational disk and is labelled "HDD, worst case". The `orfoz` partition has NVMe, but its processor and core count differ from hamsi (112
cores per node, Xeon Platinum 8480+ according to the documentation; not measured here), so a run there is a separate platform, never mixed into a hamsi table. The plan for that is in `docs/PLAN_ARALIK_2.md` (G12 to G14).
A `tmpfs` build arm would only measure the build without a disk, which E9's `UNLOGGED` arms already approximate, and is not run.

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

## Raw output of the other jobs

### hamsi124, job 7084368

```
node=hamsi124 part=hamsi job=7084368 date=2026-11-28T08:52:36Z
TMPDIR=/tmp
== lsblk
NAME    SIZE TYPE ROTA TRAN MODEL     FSTYPE MOUNTPOINT
sda     1.1T disk    1      MR9361-8i        
|-sda1    4G part    1                swap   [SWAP]
`-sda2  1.1T part    1                ext4   /
== rotational
sda rotational=1
== findmnt for benchmark paths
TARGET SOURCE    FSTYPE  SIZE AVAIL
/      /dev/sda2 ext4    1.1T    1T
TARGET SOURCE    FSTYPE  SIZE AVAIL
/      /dev/sda2 ext4    1.1T    1T
TARGET   SOURCE FSTYPE  SIZE AVAIL
/dev/shm tmpfs  tmpfs  93.5G 93.4G
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.3P
== df
Filesystem                                                                            Size  Used Avail Use% Mounted on
devtmpfs                                                                              4.0M     0  4.0M   0% /dev
tmpfs                                                                                  94G  138M   94G   1% /dev/shm
tmpfs                                                                                  38G  3.9G   34G  11% /run
/dev/sda2                                                                             1.1T   15G  1.1T   2% /
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf   13P  6.2P  6.4P  50% /arf
== nvme
ls: cannot access '/dev/nvme*': No such file or directory
== weka/lustre mounts
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
== all non-pseudo mounts
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0
/dev/sda2 / ext4 rw,relatime,stripe=64 0 0
systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=36167 0 0
none /run/credentials/systemd-tmpfiles-setup-dev.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-sysctl.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
sunrpc /var/lib/nfs/rpc_pipefs rpc_pipefs rw,relatime 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
STORAGE_CHECK_DONE
```

### barbun16, job 7084400

```
node=barbun16 part=barbun job=7084400 date=2026-11-28T10:38:55Z
TMPDIR=/tmp
== lsblk
NAME    SIZE TYPE ROTA TRAN MODEL           FSTYPE MOUNTPOINT
sda     1.1T disk    1      PERC H730P Mini        
|-sda1    4G part    1                      swap   [SWAP]
`-sda2  1.1T part    1                      ext4   /
== rotational
sda rotational=1
== findmnt for benchmark paths
TARGET SOURCE    FSTYPE  SIZE  AVAIL
/      /dev/sda2 ext4    1.1T 959.5G
TARGET SOURCE    FSTYPE  SIZE  AVAIL
/      /dev/sda2 ext4    1.1T 959.5G
TARGET   SOURCE FSTYPE  SIZE  AVAIL
/dev/shm tmpfs  tmpfs   188G 176.4G
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.3P
== df
Filesystem                                                                            Size  Used Avail Use% Mounted on
devtmpfs                                                                              4.0M     0  4.0M   0% /dev
tmpfs                                                                                 189G   12G  177G   7% /dev/shm
tmpfs                                                                                  76G  4.1G   72G   6% /run
/dev/sda2                                                                             1.1T   80G  960G   8% /
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf   13P  6.2P  6.4P  50% /arf
== nvme
ls: cannot access '/dev/nvme*': No such file or directory
== weka/lustre mounts
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
== all non-pseudo mounts
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0
/dev/sda2 / ext4 rw,relatime 0 0
systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=40253 0 0
none /run/credentials/systemd-sysctl.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup-dev.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
sunrpc /var/lib/nfs/rpc_pipefs rpc_pipefs rw,relatime 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
STORAGE_CHECK_DONE
```

### orkinos1 (smp), job 7084367

```
node=orkinos1 part=smp job=7084367 date=2026-11-28T08:24:33Z
TMPDIR=/tmp
== lsblk
NAME     SIZE TYPE ROTA TRAN MODEL     FSTYPE MOUNTPOINT
sda    372.1G disk    1      MR9363-4i        
|-sda1    64G part    1                swap   [SWAP]
|-sda2   308G part    1                ext4   /
`-sda3   100M part    1                vfat   /boot/efi
== rotational
sda rotational=1
== findmnt for benchmark paths
TARGET SOURCE    FSTYPE   SIZE AVAIL
/      /dev/sda2 ext4   302.1G 89.8G
TARGET SOURCE    FSTYPE   SIZE AVAIL
/      /dev/sda2 ext4   302.1G 89.8G
TARGET   SOURCE FSTYPE SIZE AVAIL
/dev/shm tmpfs  tmpfs    2T  1.9T
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.3P
== df
Filesystem                                                                            Size  Used Avail Use% Mounted on
devtmpfs                                                                              4.0M     0  4.0M   0% /dev
tmpfs                                                                                 2.0T   52G  2.0T   3% /dev/shm
tmpfs                                                                                 807G  3.2G  804G   1% /run
/dev/sda2                                                                             303G  197G   90G  69% /
/dev/sda3                                                                             100M   14K  100M   1% /boot/efi
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf   13P  6.2P  6.4P  50% /arf
== nvme
ls: cannot access '/dev/nvme*': No such file or directory
== weka/lustre mounts
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
== all non-pseudo mounts
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0
/dev/sda2 / ext4 rw,relatime 0 0
systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=44084 0 0
none /run/credentials/systemd-sysctl.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup-dev.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
/dev/sda3 /boot/efi vfat rw,relatime,fmask=0077,dmask=0077,codepage=437,iocharset=ascii,shortname=winnt,errors=remount-ro 0 0
none /run/credentials/systemd-tmpfiles-setup.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
sunrpc /var/lib/nfs/rpc_pipefs rpc_pipefs rw,relatime 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
STORAGE_CHECK_DONE
```

### akya7 (akya-cuda), job 7084740

```
node=akya7 part=akya-cuda job=7084740 date=2026-11-28T09:07:30Z
TMPDIR=/tmp
== lsblk
NAME     SIZE TYPE ROTA TRAN   MODEL               FSTYPE MOUNTPOINT
sda    223.6G disk    0 sata   INTEL SSDSC2KG240G8        
sdb    223.6G disk    0 sata   INTEL SSDSC2KG240G8        
|-sdb1     4G part    0                            swap   [SWAP]
`-sdb2 219.6G part    0                            ext4   /
== rotational
sda rotational=0
sdb rotational=0
== findmnt for benchmark paths
TARGET SOURCE    FSTYPE   SIZE  AVAIL
/      /dev/sdb2 ext4   215.1G 160.4G
TARGET SOURCE    FSTYPE   SIZE  AVAIL
/      /dev/sdb2 ext4   215.1G 160.4G
TARGET   SOURCE FSTYPE  SIZE  AVAIL
/dev/shm tmpfs  tmpfs   188G 186.3G
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.3P
== df
Filesystem                                                                            Size  Used Avail Use% Mounted on
devtmpfs                                                                              4.0M     0  4.0M   0% /dev
tmpfs                                                                                 189G  1.8G  187G   1% /dev/shm
tmpfs                                                                                  76G  4.1G   72G   6% /run
/dev/sdb2                                                                             216G   44G  161G  22% /
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf   13P  6.2P  6.4P  50% /arf
== nvme
ls: cannot access '/dev/nvme*': No such file or directory
== weka/lustre mounts
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
== all non-pseudo mounts
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0
/dev/sdb2 / ext4 rw,relatime 0 0
systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=53315 0 0
none /run/credentials/systemd-sysusers.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup-dev.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
sunrpc /var/lib/nfs/rpc_pipefs rpc_pipefs rw,relatime 0 0
none /run/credentials/systemd-sysctl.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
STORAGE_CHECK_DONE
```

### orfoz183 (orfoz), job 7084401

```
node=orfoz183 part=orfoz job=7084401 date=2026-11-28T09:36:32Z
TMPDIR=/tmp
== lsblk
NAME          SIZE TYPE ROTA TRAN   MODEL                     FSTYPE MOUNTPOINT
nvme0n1     894.3G disk    0 nvme   Micron_7450_MTFDKCB960TFR        
|-nvme0n1p1    50M part    0 nvme                             vfat   /boot/efi
|-nvme0n1p2    32G part    0 nvme                             swap   [SWAP]
`-nvme0n1p3 862.2G part    0 nvme                             ext4   /
== rotational
nvme0n1 rotational=0
== findmnt for benchmark paths
TARGET SOURCE         FSTYPE   SIZE AVAIL
/      /dev/nvme0n1p3 ext4   847.6G  785G
TARGET SOURCE         FSTYPE   SIZE AVAIL
/      /dev/nvme0n1p3 ext4   847.6G  785G
TARGET   SOURCE FSTYPE   SIZE  AVAIL
/dev/shm tmpfs  tmpfs  125.5G 125.5G
TARGET SOURCE                                                                               FSTYPE  SIZE AVAIL
/arf   10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf lustre 12.6P  6.3P
== df
Filesystem                                                                            Size  Used Avail Use% Mounted on
devtmpfs                                                                              4.0M     0  4.0M   0% /dev
tmpfs                                                                                 126G   68K  126G   1% /dev/shm
tmpfs                                                                                  51G  512M   50G   1% /run
/dev/nvme0n1p3                                                                        848G   20G  785G   3% /
/dev/nvme0n1p1                                                                         50M  7.0M   43M  14% /boot/efi
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf   13P  6.2P  6.4P  50% /arf
== nvme
/dev/nvme0
/dev/nvme0n1
/dev/nvme0n1p1
/dev/nvme0n1p2
/dev/nvme0n1p3
== weka/lustre mounts
/dev/nvme0n1p3 / ext4 rw,relatime 0 0
/dev/nvme0n1p1 /boot/efi vfat rw,relatime,fmask=0077,dmask=0077,codepage=437,iocharset=ascii,shortname=winnt,errors=remount-ro 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
== all non-pseudo mounts
cgroup2 /sys/fs/cgroup cgroup2 rw,nosuid,nodev,noexec,relatime,nsdelegate,memory_recursiveprot 0 0
efivarfs /sys/firmware/efi/efivars efivarfs rw,nosuid,nodev,noexec,relatime 0 0
/dev/nvme0n1p3 / ext4 rw,relatime 0 0
systemd-1 /proc/sys/fs/binfmt_misc autofs rw,relatime,fd=29,pgrp=1,timeout=0,minproto=5,maxproto=5,direct,pipe_ino=24777 0 0
none /run/credentials/systemd-sysctl.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
none /run/credentials/systemd-tmpfiles-setup-dev.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
/dev/nvme0n1p1 /boot/efi vfat rw,relatime,fmask=0077,dmask=0077,codepage=437,iocharset=ascii,shortname=winnt,errors=remount-ro 0 0
none /run/credentials/systemd-tmpfiles-setup.service ramfs ro,nosuid,nodev,noexec,relatime,mode=700 0 0
sunrpc /var/lib/nfs/rpc_pipefs rpc_pipefs rw,relatime 0 0
10.0.63.203@o2ib2,10.0.63.204@o2ib2:10.0.63.205@o2ib2,10.0.63.206@o2ib2:/lustre1/arf /arf lustre rw,checksum,flock,nouser_xattr,lruresize,lazystatfs,nouser_fid2path,verbose,noencrypt 0 0
STORAGE_CHECK_DONE
```
