#!/usr/bin/env python3
import argparse
import json
import statistics
import subprocess
import threading
import time
from pathlib import Path


def run_once(cmd: list[str]) -> float:
    start = time.perf_counter_ns()
    subprocess.run(cmd, check=True)
    end = time.perf_counter_ns()
    return (end - start) / 1_000_000.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True, help="Shell command to run per iteration")
    parser.add_argument("--iterations", type=int, default=8)
    parser.add_argument("--parallelism", type=int, default=2)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    cmd = args.command.split()
    samples: list[float] = []
    samples_lock = threading.Lock()

    def worker(iteration_count: int) -> None:
        local = []
        for _ in range(iteration_count):
            local.append(run_once(cmd))
        with samples_lock:
            samples.extend(local)

    base = args.iterations // args.parallelism
    rem = args.iterations % args.parallelism
    threads = []
    for index in range(args.parallelism):
        thread_iters = base + (1 if index < rem else 0)
        if thread_iters <= 0:
            continue
        t = threading.Thread(target=worker, args=(thread_iters,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    samples.sort()
    report = {
        "schemaVersion": 1,
        "benchmark": "pipeline_concurrency",
        "iterations": len(samples),
        "parallelism": args.parallelism,
        "samplesMs": samples,
        "p50Ms": statistics.median(samples) if samples else 0.0,
        "p95Ms": samples[min(len(samples) - 1, max(0, int(len(samples) * 0.95) - 1))] if samples else 0.0,
        "maxMs": samples[-1] if samples else 0.0,
        "command": cmd,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
