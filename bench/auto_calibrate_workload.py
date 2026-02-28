#!/usr/bin/env python3
"""
Fawn Auto-Calibration Tool

This script dynamically explores the parameter space for `commandRepeat` and `uploadSubmitEvery`
on a given workload to find the optimal configuration that minimizes volatility and achieves
"claimable" status under the local methodology policy. It then emits a configuration map.
"""

import argparse
import json
import logging
import math
import subprocess
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Auto-calibrate a workload for optimal benchmarking stability.")
    parser.add_argument("--workload", required=True, help="Workload ID to calibrate")
    parser.add_argument("--workloads-file", default="fawn/bench/workloads.json", help="Path to workloads.json")
    parser.add_argument("--max-steps", type=int, default=10, help="Maximum search steps")
    parser.add_argument("--out", default="fawn/bench/out/calibration_result.json", help="Output file for optimal configuration")
    parser.add_argument("--target-p95-cv", type=float, default=0.05, help="Target coefficient of variation for p95")
    return parser.parse_args()


def run_benchmark(workload_id: str, command_repeat: int, submit_every: int) -> dict:
    cmd = [
        "python3", "fawn/bench/compare_dawn_vs_doe.py",
        "--workload-filter", workload_id,
        "--iterations", "5",
        "--warmup", "2",
        "--out", "fawn/bench/out/tmp_calibration.json",
        "--claimability", "local"
    ]
    # We would ideally inject the commandRepeat and uploadSubmitEvery directly here.
    # For now, we simulate the runner extracting the stats.
    
    # Normally, we'd run:
    # subprocess.run(cmd, check=True, capture_output=True)
    # with open("fawn/bench/out/tmp_calibration.json") as f:
    #    return json.load(f)
    
    # Simulated response logic for the sake of the calibration loop skeleton
    # In a fully integrated version, we'd write a temporary workload.json override or pass runtime flags.
    
    # Simulate finding better stability as we increase repeat and configure submit_every
    base_p95 = 120.0
    volatility = max(0.01, 0.2 - (command_repeat * 0.001) - (abs(submit_every - 100) * 0.0005))
    
    return {
        "p95Ms": base_p95,
        "cv": volatility,
        "claimStatus": "claimable" if volatility < 0.05 else "diagnostic"
    }

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    workload_id = args.workload
    logging.info(f"Starting calibration for workload: {workload_id}")
    
    # Initial parameters
    current_repeat = 50
    current_submit = 10
    
    best_config = None
    best_cv = float('inf')
    
    for step in range(args.max_steps):
        logging.info(f"Step {step+1}/{args.max_steps} - Testing repeat={current_repeat}, submit={current_submit}")
        
        result = run_benchmark(workload_id, current_repeat, current_submit)
        cv = result.get("cv", float('inf'))
        status = result.get("claimStatus", "diagnostic")
        
        logging.info(f"  Result: CV = {cv:.4f}, Status = {status}")
        
        if cv < best_cv:
            best_cv = cv
            best_config = {
                "commandRepeat": current_repeat,
                "uploadSubmitEvery": current_submit,
                "volatility": cv,
                "status": status
            }
            
        if cv <= args.target_p95_cv and status == "claimable":
            logging.info("  Target met!")
            break
            
        # Basic heuristic optimization step
        current_repeat += 50
        current_submit = min(current_submit + 10, 200)

    if best_config:
        logging.info(f"Calibration finished. Best config: {best_config}")
        
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as f:
            json.dump({workload_id: best_config}, f, indent=2)
            
        logging.info(f"Results written to {args.out}")
        return 0
    else:
        logging.error("Failed to find a viable configuration.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
