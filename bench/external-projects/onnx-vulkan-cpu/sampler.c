#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

/* Repository-only Linux/x86-64 CPU attribution; bounded candidate frame reads. */
static int output = -1;
static timer_t timer;
static int sampling;
static volatile sig_atomic_t active;
static volatile sig_atomic_t dropped;
static uint64_t thread_start, process_start, thread_total, process_total, runs;
enum { PROC_CAPACITY = 512, STACK_CAPACITY = 16 };
static int main_tid, spans;
static uintptr_t stack_low, stack_high;
static __thread volatile sig_atomic_t site __attribute__((tls_model("initial-exec"))) = -1;
static __thread int main_thread __attribute__((tls_model("initial-exec")));
static struct { unsigned index; uint64_t start, children; } stack[STACK_CAPACITY];
static unsigned depth;
static struct { uint64_t count, inclusive, exclusive; } procs[PROC_CAPACITY];

static uint64_t now(clockid_t clock) {
    struct timespec value;
    if (clock_gettime(clock, &value)) { perror("CPU probe clock"); exit(98); }
    return (uint64_t)value.tv_sec * 1000000000ULL + value.tv_nsec;
}

static void sample(int signal, siginfo_t *info, void *context) {
    (void)signal;
    int saved_errno = errno;
    if (active) {
        ucontext_t *state = context;
        uint64_t row[16] = {
            (uint64_t)state->uc_mcontext.gregs[REG_RIP],
            (uint64_t)syscall(SYS_gettid), (uint64_t)info->si_overrun,
            site < 0 ? UINT64_MAX : (uint64_t)site
        };
        uintptr_t frame = state->uc_mcontext.gregs[REG_RBP];
        uintptr_t stack_pointer = state->uc_mcontext.gregs[REG_RSP];
        for (unsigned index = 0; index < 8; ++index) {
            if (frame < stack_pointer || frame < stack_low ||
                frame > stack_high - 2 * sizeof(uintptr_t) || frame % sizeof(uintptr_t)) break;
            const uintptr_t *words = (const uintptr_t *)frame;
            row[5 + index] = words[1];
            ++row[4];
            if (words[0] <= frame) break;
            frame = words[0];
        }
        row[13] = state->uc_mcontext.gregs[REG_RDX];
        row[14] = state->uc_mcontext.gregs[REG_RDI];
        row[15] = state->uc_mcontext.gregs[REG_RSI];
        if (write(output, row, sizeof(row)) != sizeof(row)) dropped = 1;
    }
    errno = saved_errno;
}

__attribute__((constructor)) static void initialize(void) {
    const char *path = getenv("DOE_CPU_SAMPLES");
    if (!path) return;
    main_tid = syscall(SYS_gettid);
    main_thread = 1;
    pthread_attr_t attributes;
    void *stack_address;
    size_t stack_size;
    if (pthread_getattr_np(pthread_self(), &attributes) ||
        pthread_attr_getstack(&attributes, &stack_address, &stack_size) ||
        pthread_attr_destroy(&attributes)) {
        fputs("CPU probe stack unavailable\n", stderr); exit(98);
    }
    stack_low = (uintptr_t)stack_address;
    stack_high = stack_low + stack_size;
    spans = getenv("DOE_CPU_SPANS") != NULL;
    output = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0600);
    if (output < 0) { perror("CPU probe output"); exit(98); }
    const char *period = getenv("DOE_CPU_PERIOD_US");
    if (!period) { fputs("Missing CPU period\n", stderr); exit(98); }
    char *end;
    long interval = strtol(period, &end, 10);
    if (*end || interval < 0 || interval > 1000000) {
        fputs("Invalid CPU period\n", stderr); exit(98);
    }
    if (!interval) return;
    int signal = SIGRTMIN + 6;
    struct sigaction previous, action = {0};
    if (sigaction(signal, NULL, &previous) || previous.sa_handler != SIG_DFL) {
        fputs("CPU signal already owned\n", stderr); exit(98);
    }
    action.sa_sigaction = sample;
    action.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&action.sa_mask);
    if (sigaction(signal, &action, NULL)) { perror("CPU probe signal"); exit(98); }
    struct sigevent event = {0};
    event.sigev_notify = SIGEV_THREAD_ID;
    event.sigev_signo = signal;
    event._sigev_un._tid = syscall(SYS_gettid);
    if (timer_create(CLOCK_THREAD_CPUTIME_ID, &event, &timer)) {
        perror("CPU probe timer"); exit(98);
    }
    struct itimerspec cadence = {0};
    cadence.it_interval.tv_sec = interval / 1000000;
    cadence.it_interval.tv_nsec = (interval % 1000000) * 1000;
    cadence.it_value = cadence.it_interval;
    if (timer_settime(timer, 0, &cadence, NULL)) { perror("CPU probe arm"); exit(98); }
    sampling = 1;
}

void doeCpuProbeBegin(void) {
    process_start = now(CLOCK_PROCESS_CPUTIME_ID);
    thread_start = now(CLOCK_THREAD_CPUTIME_ID);
    active = 1;
}

void doeCpuProbeEnter(unsigned index) {
    if (!main_thread || !active) return;
    if (index >= PROC_CAPACITY || depth == STACK_CAPACITY) {
        fputs("CPU probe span capacity exceeded\n", stderr); exit(98);
    }
    stack[depth].index = index;
    stack[depth].children = 0;
    stack[depth].start = spans ? now(CLOCK_THREAD_CPUTIME_ID) : 0;
    ++depth;
    site = index;
}

void doeCpuProbeLeave(void) {
    if (!main_thread || !active) return;
    if (!depth) { fputs("CPU probe unbalanced spans\n", stderr); exit(98); }
    --depth;
    if (spans) {
        uint64_t elapsed = now(CLOCK_THREAD_CPUTIME_ID) - stack[depth].start;
        unsigned index = stack[depth].index;
        ++procs[index].count;
        procs[index].inclusive += elapsed;
        procs[index].exclusive += elapsed - stack[depth].children;
        if (depth) stack[depth - 1].children += elapsed;
    }
    site = depth ? (sig_atomic_t)stack[depth - 1].index : -1;
}

void doeCpuProbeEnd(void) {
    if (depth) { fputs("CPU probe retained active spans\n", stderr); exit(98); }
    active = 0;
    thread_total += now(CLOCK_THREAD_CPUTIME_ID) - thread_start;
    process_total += now(CLOCK_PROCESS_CPUTIME_ID) - process_start;
    ++runs;
}

void doeCpuProbeMaps(void) {
    const char *path = getenv("DOE_CPU_MAPS");
    if (!path) return;
    FILE *source = fopen("/proc/self/maps", "r");
    FILE *destination = fopen(path, "wx");
    if (!source || !destination) { perror("CPU probe mappings"); _exit(98); }
    char buffer[4096];
    size_t count;
    while ((count = fread(buffer, 1, sizeof(buffer), source)))
        if (fwrite(buffer, 1, count, destination) != count) _exit(98);
    if (ferror(source) || fclose(source) || fclose(destination)) _exit(98);
}

__attribute__((destructor)) static void finish(void) {
    active = 0;
    if (sampling && timer_delete(timer)) { perror("CPU probe delete"); _exit(98); }
    if (output >= 0 && close(output)) { perror("CPU probe close"); _exit(98); }
    printf("CpuProbeSummary %llu %llu %llu %d\n",
        (unsigned long long)runs, (unsigned long long)thread_total,
        (unsigned long long)process_total, (int)dropped);
    for (unsigned index = 0; index < PROC_CAPACITY; ++index)
        if (procs[index].count) printf("CpuProbeProc %u %llu %llu %llu\n", index,
            (unsigned long long)procs[index].count,
            (unsigned long long)procs[index].inclusive,
            (unsigned long long)procs[index].exclusive);
}
