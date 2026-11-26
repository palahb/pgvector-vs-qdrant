# How the engines were built, and which instruction sets they run (recorded 26 November 2026)

Read from the unpacked images (`apptainer build --sandbox`, `runtime/pgroot` and `runtime/qroot` on the cluster) and from the
hardware record of a result file (`host` of `results/E19.../pg_rep1_pg/result.json`, node hamsi45).

## Hardware (every node of the `hamsi` partition used here)

Intel Xeon Gold 6258R @ 2.70 GHz (Cascade Lake), 2 sockets x 28 cores, SMT off. Flags relevant to vector code: `sse4_2 avx avx2 fma f16c
avx512f avx512dq avx512cd avx512bw avx512vl avx512_vnni`. Governor `performance`. `perf_event_paranoid=2`: user-space counters only.

## PostgreSQL 17.11 (image `pgvector-0.8.6-pg17.sif`, Debian pgdg12+2)

`pg_config --cflags`: `-O2 -g -fstack-protector-strong -fno-omit-frame-pointer -fno-strict-aliasing -fwrapv ...`, GCC 12.2.0 (Debian
12.2.0-14+deb12u1). The `postgres` binary is stripped (no `.comment`, no static symbols), which is why part of its profile stays
unresolved (E19).

## pgvector 0.8.6 (`vector.so`)

Compiler record in the DWARF producer string: `GNU C17 12.2.0 -mtune=generic -march=x86-64 -g -O2 -fno-strict-aliasing -fwrapv
-fstack-protector-strong -fno-omit-frame-pointer -ftree-vectorize -fassociative-math -fno-signed-zeros -fno-trapping-math -fPIC
-fvisibility=hidden`. The target is the **baseline x86-64**, not `-march=native`. The distance functions are multi-versioned: the
object holds `VectorInnerProduct`, `VectorCosineSimilarity`, `VectorL1Distance` and `VectorL2SquaredDistance` with a `.fma` clone
(chosen at run time on a CPU with FMA), and the `halfvec` functions have `...F16c` variants. There is **no AVX-512 clone**. The
profiles of E19 show the `.fma` clone executing for `vector` (`VectorInnerProduct.fma`, 24.8% of the samples at 1M x 1024) and
`HalfvecInnerProductF16c` for `halfvec` (smoke profile).

## Qdrant 1.19.1 (image `qdrant-v1.19.1.sif`)

`.comment`: `rustc version 1.98.0`, `Debian clang version 14.0.6`. The binary contains run-time feature tests for `avx`, `fma`,
`avx512f`, `avx512vl` and `avx512vpopcntdq` and AVX-512 VNNI kernels for quantized scoring (`score_4bit_internal_avx512_vnni`,
`dotprod_raw_avx512_vnni`). The float32 profiles of E19 show `segment::spaces::simple_avx::dot_similarity_avx` carrying 76-77% of the
samples. The int8 profiles were recorded only in the smoke test; which kernel scores int8 in E20 was not checked.

## What this means for the comparison

Both engines compute float32 cosine distance with AVX/FMA code on a CPU that also has AVX-512: pgvector cannot use AVX-512 for `vector`
by construction, and the Qdrant float path that ran is the AVX one. The distance kernels of the two engines therefore use the same
instruction family, so a difference in per-distance cost is not explained by AVX-512 against AVX2. The E7 kernel probe (scalar 1,504,
AVX2 282, AVX-512 248 ns per 1024-d distance) bounds the distance count from above (E19); it was compiled with `-O3` in
`bench/distance_kernel.c` and is not either engine's code.

## Reproduce

```
apptainer build --sandbox runtime/pgroot images/pgvector-0.8.6-pg17.sif
apptainer build --sandbox runtime/qroot  images/qdrant-v1.19.1.sif
apptainer exec --cleanenv images/pgvector-0.8.6-pg17.sif pg_config --version --cflags
readelf --debug-dump=info runtime/pgroot/usr/lib/postgresql/17/lib/vector.so | grep -m1 DW_AT_producer
nm runtime/pgroot/usr/lib/postgresql/17/lib/vector.so | grep -E '\.fma|F16c|avx512'
readelf -p .comment runtime/qroot/qdrant/qdrant
strings -n 8 runtime/qroot/qdrant/qdrant | grep -E 'avx|fma'
```
