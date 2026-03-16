#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "dropin_benchmark_ops.h"

typedef struct StatsSummary {
    uint64_t min_ns;
    uint64_t max_ns;
    uint64_t p50_ns;
    uint64_t p95_ns;
    double mean_ns;
} StatsSummary;

static uint64_t monotonic_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000ull) + (uint64_t)ts.tv_nsec;
}

static int compare_u64(const void* left, const void* right) {
    const uint64_t a = *(const uint64_t*)left;
    const uint64_t b = *(const uint64_t*)right;
    if (a < b) {
        return -1;
    }
    if (a > b) {
        return 1;
    }
    return 0;
}

static uint64_t percentile_value(const uint64_t* sorted_samples, size_t count, size_t percentile) {
    if (count == 0) {
        return 0;
    }
    const size_t index = ((count - 1) * percentile) / 100;
    return sorted_samples[index];
}

static StatsSummary compute_summary(const uint64_t* samples, size_t count) {
    StatsSummary summary = {
        .min_ns = 0,
        .max_ns = 0,
        .p50_ns = 0,
        .p95_ns = 0,
        .mean_ns = 0.0,
    };

    if (count == 0 || samples == NULL) {
        return summary;
    }

    uint64_t* sorted = (uint64_t*)malloc(sizeof(uint64_t) * count);
    if (sorted == NULL) {
        return summary;
    }

    uint64_t sum = 0;
    for (size_t i = 0; i < count; ++i) {
        sorted[i] = samples[i];
        sum += samples[i];
    }

    qsort(sorted, count, sizeof(uint64_t), compare_u64);

    summary.min_ns = sorted[0];
    summary.max_ns = sorted[count - 1];
    summary.p50_ns = percentile_value(sorted, count, 50);
    summary.p95_ns = percentile_value(sorted, count, 95);
    summary.mean_ns = (double)sum / (double)count;

    free(sorted);
    return summary;
}

static bool parse_uint32_arg(const char* value, uint32_t* out) {
    char* end_ptr = NULL;
    unsigned long parsed = strtoul(value, &end_ptr, 10);
    if (end_ptr == value || *end_ptr != '\0') {
        return false;
    }
    if (parsed == 0 || parsed > 1000000ul) {
        return false;
    }
    *out = (uint32_t)parsed;
    return true;
}

static void print_benchmark_json(
    const char* id,
    const char* class_name,
    size_t samples,
    const StatsSummary* summary,
    bool* first
) {
    if (!*first) {
        printf(",");
    }
    *first = false;
    printf("{\"id\":\"%s\",\"class\":\"%s\",\"unit\":\"ns\",\"samples\":%zu,", id, class_name, samples);
    printf("\"stats\":{\"minNs\":%llu,\"maxNs\":%llu,\"meanNs\":%.2f,\"p50Ns\":%llu,\"p95Ns\":%llu}}",
        (unsigned long long)summary->min_ns,
        (unsigned long long)summary->max_ns,
        summary->mean_ns,
        (unsigned long long)summary->p50_ns,
        (unsigned long long)summary->p95_ns);
}

int main(int argc, char** argv) {
    uint32_t micro_iterations = 30;
    uint32_t e2e_iterations = 10;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--micro-iterations") == 0 && (i + 1) < argc) {
            if (!parse_uint32_arg(argv[i + 1], &micro_iterations)) {
                fprintf(stderr, "invalid --micro-iterations value: %s\n", argv[i + 1]);
                return 2;
            }
            i += 1;
            continue;
        }
        if (strcmp(argv[i], "--e2e-iterations") == 0 && (i + 1) < argc) {
            if (!parse_uint32_arg(argv[i + 1], &e2e_iterations)) {
                fprintf(stderr, "invalid --e2e-iterations value: %s\n", argv[i + 1]);
                return 2;
            }
            i += 1;
            continue;
        }
        fprintf(stderr, "unknown argument: %s\n", argv[i]);
        return 2;
    }

    uint64_t* instance_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* cmd_finish_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* submit_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* write_1kb_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* write_4kb_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* write_64kb_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* buffer_create_4kb_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));
    uint64_t* buffer_create_64kb_samples = (uint64_t*)calloc(micro_iterations, sizeof(uint64_t));

    uint64_t* e2e_device_only_samples = (uint64_t*)calloc(e2e_iterations, sizeof(uint64_t));
    uint64_t* e2e_queue_submit_samples = (uint64_t*)calloc(e2e_iterations, sizeof(uint64_t));
    uint64_t* e2e_write_4kb_samples = (uint64_t*)calloc(e2e_iterations, sizeof(uint64_t));
    uint64_t* e2e_write_64kb_samples = (uint64_t*)calloc(e2e_iterations, sizeof(uint64_t));
    uint64_t* e2e_queue_ops_samples = (uint64_t*)calloc(e2e_iterations, sizeof(uint64_t));

    if (instance_samples == NULL || cmd_finish_samples == NULL || submit_samples == NULL ||
        write_1kb_samples == NULL || write_4kb_samples == NULL || write_64kb_samples == NULL ||
        buffer_create_4kb_samples == NULL || buffer_create_64kb_samples == NULL ||
        e2e_device_only_samples == NULL || e2e_queue_submit_samples == NULL ||
        e2e_write_4kb_samples == NULL || e2e_write_64kb_samples == NULL ||
        e2e_queue_ops_samples == NULL) {
        fprintf(stderr, "allocation failure\n");
        free(instance_samples);
        free(cmd_finish_samples);
        free(submit_samples);
        free(write_1kb_samples);
        free(write_4kb_samples);
        free(write_64kb_samples);
        free(buffer_create_4kb_samples);
        free(buffer_create_64kb_samples);
        free(e2e_device_only_samples);
        free(e2e_queue_submit_samples);
        free(e2e_write_4kb_samples);
        free(e2e_write_64kb_samples);
        free(e2e_queue_ops_samples);
        return 1;
    }

    const char* failure = "none";
    bool pass = true;

    size_t instance_count = 0;
    for (; instance_count < micro_iterations; ++instance_count) {
        const uint64_t start_ns = monotonic_time_ns();
        if (!dropin_bench_instance_create_destroy_once(&failure)) {
            pass = false;
            break;
        }
        instance_samples[instance_count] = monotonic_time_ns() - start_ns;
    }

    DropinContext micro_context;
    bool micro_context_ready = false;
    size_t cmd_finish_count = 0;
    size_t submit_count = 0;
    size_t write_1kb_count = 0;
    size_t write_4kb_count = 0;
    size_t write_64kb_count = 0;
    size_t buffer_create_4kb_count = 0;
    size_t buffer_create_64kb_count = 0;

    if (pass) {
        if (!dropin_bench_create_context(&micro_context, &failure)) {
            pass = false;
        } else {
            micro_context_ready = true;
        }
    }

    if (pass) {
        for (; cmd_finish_count < micro_iterations; ++cmd_finish_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_command_encoder_finish_empty_once(&micro_context, &failure)) {
                pass = false;
                break;
            }
            cmd_finish_samples[cmd_finish_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; submit_count < micro_iterations; ++submit_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_queue_submit_empty_once(&micro_context, &failure)) {
                pass = false;
                break;
            }
            submit_samples[submit_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; write_1kb_count < micro_iterations; ++write_1kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_queue_write_buffer_size_once(&micro_context, BENCH_WRITE_SMALL, &failure)) {
                pass = false;
                break;
            }
            write_1kb_samples[write_1kb_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; write_4kb_count < micro_iterations; ++write_4kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_queue_write_buffer_size_once(&micro_context, BENCH_WRITE_MEDIUM, &failure)) {
                pass = false;
                break;
            }
            write_4kb_samples[write_4kb_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; write_64kb_count < micro_iterations; ++write_64kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_queue_write_buffer_size_once(&micro_context, BENCH_WRITE_LARGE, &failure)) {
                pass = false;
                break;
            }
            write_64kb_samples[write_64kb_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; buffer_create_4kb_count < micro_iterations; ++buffer_create_4kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_buffer_create_destroy_once(&micro_context, BENCH_WRITE_MEDIUM, &failure)) {
                pass = false;
                break;
            }
            buffer_create_4kb_samples[buffer_create_4kb_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (pass) {
        for (; buffer_create_64kb_count < micro_iterations; ++buffer_create_64kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_buffer_create_destroy_once(&micro_context, BENCH_WRITE_LARGE, &failure)) {
                pass = false;
                break;
            }
            buffer_create_64kb_samples[buffer_create_64kb_count] = monotonic_time_ns() - start_ns;
        }
    }

    if (micro_context_ready) {
        dropin_bench_destroy_context(&micro_context);
    }

    size_t e2e_device_only_count = 0;
    size_t e2e_queue_submit_count = 0;
    size_t e2e_write_4kb_count = 0;
    size_t e2e_write_64kb_count = 0;
    size_t e2e_queue_ops_count = 0;
    if (pass) {
        for (; e2e_device_only_count < e2e_iterations; ++e2e_device_only_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_full_lifecycle_device_only_once(&failure)) {
                pass = false;
                break;
            }
            e2e_device_only_samples[e2e_device_only_count] = monotonic_time_ns() - start_ns;
        }
    }
    if (pass) {
        for (; e2e_queue_submit_count < e2e_iterations; ++e2e_queue_submit_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_full_lifecycle_queue_submit_once(&failure)) {
                pass = false;
                break;
            }
            e2e_queue_submit_samples[e2e_queue_submit_count] = monotonic_time_ns() - start_ns;
        }
    }
    if (pass) {
        for (; e2e_write_4kb_count < e2e_iterations; ++e2e_write_4kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_full_lifecycle_write_size_once(BENCH_WRITE_MEDIUM, &failure)) {
                pass = false;
                break;
            }
            e2e_write_4kb_samples[e2e_write_4kb_count] = monotonic_time_ns() - start_ns;
        }
    }
    if (pass) {
        for (; e2e_write_64kb_count < e2e_iterations; ++e2e_write_64kb_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_full_lifecycle_write_size_once(BENCH_WRITE_LARGE, &failure)) {
                pass = false;
                break;
            }
            e2e_write_64kb_samples[e2e_write_64kb_count] = monotonic_time_ns() - start_ns;
        }
    }
    if (pass) {
        for (; e2e_queue_ops_count < e2e_iterations; ++e2e_queue_ops_count) {
            const uint64_t start_ns = monotonic_time_ns();
            if (!dropin_bench_full_lifecycle_queue_ops_once(&failure)) {
                pass = false;
                break;
            }
            e2e_queue_ops_samples[e2e_queue_ops_count] = monotonic_time_ns() - start_ns;
        }
    }

    const StatsSummary instance_summary = compute_summary(instance_samples, instance_count);
    const StatsSummary cmd_finish_summary = compute_summary(cmd_finish_samples, cmd_finish_count);
    const StatsSummary submit_summary = compute_summary(submit_samples, submit_count);
    const StatsSummary write_1kb_summary = compute_summary(write_1kb_samples, write_1kb_count);
    const StatsSummary write_4kb_summary = compute_summary(write_4kb_samples, write_4kb_count);
    const StatsSummary write_64kb_summary = compute_summary(write_64kb_samples, write_64kb_count);
    const StatsSummary buffer_create_4kb_summary = compute_summary(buffer_create_4kb_samples, buffer_create_4kb_count);
    const StatsSummary buffer_create_64kb_summary = compute_summary(buffer_create_64kb_samples, buffer_create_64kb_count);

    const StatsSummary e2e_device_only_summary = compute_summary(e2e_device_only_samples, e2e_device_only_count);
    const StatsSummary e2e_queue_submit_summary = compute_summary(e2e_queue_submit_samples, e2e_queue_submit_count);
    const StatsSummary e2e_write_4kb_summary = compute_summary(e2e_write_4kb_samples, e2e_write_4kb_count);
    const StatsSummary e2e_write_64kb_summary = compute_summary(e2e_write_64kb_samples, e2e_write_64kb_count);
    const StatsSummary e2e_queue_ops_summary = compute_summary(e2e_queue_ops_samples, e2e_queue_ops_count);

    printf("{\"schemaVersion\":1,\"pass\":%s,\"failure\":\"%s\",", pass ? "true" : "false", failure);
    printf("\"microIterationsRequested\":%u,\"e2eIterationsRequested\":%u,", micro_iterations, e2e_iterations);
    printf("\"benchmarks\":[");
    bool first_benchmark = true;
    print_benchmark_json("instance_create_destroy", "micro", instance_count, &instance_summary, &first_benchmark);
    print_benchmark_json("command_encoder_finish_empty", "micro", cmd_finish_count, &cmd_finish_summary, &first_benchmark);
    print_benchmark_json("queue_submit_empty", "micro", submit_count, &submit_summary, &first_benchmark);
    print_benchmark_json("queue_write_buffer_1kb", "micro", write_1kb_count, &write_1kb_summary, &first_benchmark);
    print_benchmark_json("queue_write_buffer_4kb", "micro", write_4kb_count, &write_4kb_summary, &first_benchmark);
    print_benchmark_json("queue_write_buffer_64kb", "micro", write_64kb_count, &write_64kb_summary, &first_benchmark);
    print_benchmark_json("buffer_create_destroy_4kb", "micro", buffer_create_4kb_count, &buffer_create_4kb_summary, &first_benchmark);
    print_benchmark_json("buffer_create_destroy_64kb", "micro", buffer_create_64kb_count, &buffer_create_64kb_summary, &first_benchmark);
    print_benchmark_json("full_lifecycle_device_only", "end_to_end", e2e_device_only_count, &e2e_device_only_summary, &first_benchmark);
    print_benchmark_json("full_lifecycle_queue_submit", "end_to_end", e2e_queue_submit_count, &e2e_queue_submit_summary, &first_benchmark);
    print_benchmark_json("full_lifecycle_write_4kb", "end_to_end", e2e_write_4kb_count, &e2e_write_4kb_summary, &first_benchmark);
    print_benchmark_json("full_lifecycle_write_64kb", "end_to_end", e2e_write_64kb_count, &e2e_write_64kb_summary, &first_benchmark);
    print_benchmark_json("full_lifecycle_queue_ops", "end_to_end", e2e_queue_ops_count, &e2e_queue_ops_summary, &first_benchmark);

    printf("]}\n");

    free(instance_samples);
    free(cmd_finish_samples);
    free(submit_samples);
    free(write_1kb_samples);
    free(write_4kb_samples);
    free(write_64kb_samples);
    free(buffer_create_4kb_samples);
    free(buffer_create_64kb_samples);
    free(e2e_device_only_samples);
    free(e2e_queue_submit_samples);
    free(e2e_write_4kb_samples);
    free(e2e_write_64kb_samples);
    free(e2e_queue_ops_samples);

    return pass ? 0 : 1;
}
