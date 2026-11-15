#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(__x86_64__) || defined(__i386__)
#include <immintrin.h>
#define X86_RUNTIME_DISPATCH 1
#else
#define X86_RUNTIME_DISPATCH 0
#endif

#if defined(__GNUC__) && !defined(__clang__)
#define NOINLINE __attribute__((noinline))
#define SCALAR_ATTR __attribute__((noinline, optimize("no-tree-vectorize")))
#else
#define NOINLINE __attribute__((noinline))
#define SCALAR_ATTR __attribute__((noinline))
#endif

typedef float (*dot_fn)(const float *, const float *, size_t);

static SCALAR_ATTR float dot_scalar(const float *a, const float *b, size_t n) {
    float sum = 0.0f;
    for (size_t i = 0; i < n; ++i) sum += a[i] * b[i];
    return sum;
}

#if X86_RUNTIME_DISPATCH && defined(__GNUC__)
static NOINLINE __attribute__((target("avx2,fma")))
float dot_avx2(const float *a, const float *b, size_t n) {
    __m256 acc = _mm256_setzero_ps();
    size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        acc = _mm256_fmadd_ps(_mm256_loadu_ps(a + i), _mm256_loadu_ps(b + i), acc);
    }
    float lanes[8];
    _mm256_storeu_ps(lanes, acc);
    float sum = 0.0f;
    for (int j = 0; j < 8; ++j) sum += lanes[j];
    for (; i < n; ++i) sum += a[i] * b[i];
    return sum;
}

static NOINLINE __attribute__((target("avx512f,fma")))
float dot_avx512(const float *a, const float *b, size_t n) {
    __m512 acc = _mm512_setzero_ps();
    size_t i = 0;
    for (; i + 16 <= n; i += 16) {
        acc = _mm512_fmadd_ps(_mm512_loadu_ps(a + i), _mm512_loadu_ps(b + i), acc);
    }
    float lanes[16];
    _mm512_storeu_ps(lanes, acc);
    float sum = 0.0f;
    for (int j = 0; j < 16; ++j) sum += lanes[j];
    for (; i < n; ++i) sum += a[i] * b[i];
    return sum;
}
#endif

static uint64_t rng_state = UINT64_C(0x6a09e667f3bcc909);

static float random_float(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return ((float)(rng_state & UINT64_C(0xffffff)) / 8388608.0f) - 1.0f;
}

static double seconds(void) {
    struct timespec t;
#ifdef CLOCK_MONOTONIC_RAW
    const clockid_t clock_id = CLOCK_MONOTONIC_RAW;
#else
    const clockid_t clock_id = CLOCK_MONOTONIC;
#endif
    if (clock_gettime(clock_id, &t) != 0) {
        perror("clock_gettime");
        exit(2);
    }
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}

static void run_kernel(const char *name, dot_fn fn, const float *base, const float *query,
                       size_t vectors, size_t dim, size_t passes) {
    volatile float checksum = 0.0f;
    for (size_t i = 0; i < vectors; ++i) checksum += fn(base + i * dim, query, dim);
    double t0 = seconds();
    for (size_t p = 0; p < passes; ++p) {
        float pass_sum = 0.0f;
        for (size_t i = 0; i < vectors; ++i) pass_sum += fn(base + i * dim, query, dim);
        checksum += pass_sum;
    }
    double elapsed = seconds() - t0;
    double distances = (double)vectors * (double)passes;
    double bytes = distances * (double)dim * 2.0 * sizeof(float);
    double flops = distances * (double)dim * 2.0;
    printf("{\"kernel\":\"%s\",\"vectors\":%zu,\"dim\":%zu,\"passes\":%zu,"
           "\"seconds\":%.9f,\"ns_per_distance\":%.6f,\"gib_per_s\":%.6f,"
           "\"gflop_per_s\":%.6f,\"checksum\":%.9g}\n",
           name, vectors, dim, passes, elapsed, elapsed * 1e9 / distances,
           bytes / elapsed / (1024.0 * 1024.0 * 1024.0), flops / elapsed / 1e9,
           (double)checksum);
}

static size_t parse_size(const char *text, const char *name) {
    char *end = NULL;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno || !end || *end || value == 0) {
        fprintf(stderr, "invalid %s: %s\n", name, text);
        exit(2);
    }
    return (size_t)value;
}

int main(int argc, char **argv) {
    size_t vectors = 16384, dim = 1024, passes = 12;
    for (int i = 1; i < argc; ++i) {
        if (i + 1 >= argc) {
            fprintf(stderr, "usage: %s [--vectors N] [--dim N] [--passes N]\n", argv[0]);
            return 2;
        }
        if (!strcmp(argv[i], "--vectors")) vectors = parse_size(argv[++i], "vectors");
        else if (!strcmp(argv[i], "--dim")) dim = parse_size(argv[++i], "dim");
        else if (!strcmp(argv[i], "--passes")) passes = parse_size(argv[++i], "passes");
        else {
            fprintf(stderr, "unknown option: %s\n", argv[i]);
            return 2;
        }
    }
    if (vectors > SIZE_MAX / dim || vectors * dim > SIZE_MAX / sizeof(float)) {
        fprintf(stderr, "allocation size overflow\n");
        return 2;
    }
    float *base = NULL, *query = NULL;
    if (posix_memalign((void **)&base, 64, vectors * dim * sizeof(float)) ||
        posix_memalign((void **)&query, 64, dim * sizeof(float))) {
        fprintf(stderr, "aligned allocation failed\n");
        free(base);
        free(query);
        return 2;
    }
    for (size_t i = 0; i < vectors * dim; ++i) base[i] = random_float();
    for (size_t i = 0; i < dim; ++i) query[i] = random_float();

    run_kernel("scalar", dot_scalar, base, query, vectors, dim, passes);
#if X86_RUNTIME_DISPATCH && defined(__GNUC__)
    __builtin_cpu_init();
    if (__builtin_cpu_supports("avx2") && __builtin_cpu_supports("fma"))
        run_kernel("avx2_fma", dot_avx2, base, query, vectors, dim, passes);
    if (__builtin_cpu_supports("avx512f") && __builtin_cpu_supports("fma"))
        run_kernel("avx512f_fma", dot_avx512, base, query, vectors, dim, passes);
#endif
    free(base);
    free(query);
    return 0;
}
