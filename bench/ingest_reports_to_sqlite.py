#!/usr/bin/env python3
"""
Fawn SQLite Report Ingestor

This script ingests Fawn benchmark reports (typically emitted by compare_dawn_vs_doe.py)
into a local SQLite database for historical trend analysis.
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

def parse_args():
    parser = argparse.ArgumentParser(description="Ingest Fawn Benchmark JSON into SQLite")
    parser.add_argument("--db", default="fawn/bench/out/fawn_benchmarks.sqlite", help="Path to SQLite database")
    parser.add_argument("--report", required=True, help="Path to Fawn benchmark report JSON")
    return parser.parse_args()

def setup_database(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            workload_contract_sha256 TEXT NOT NULL,
            claim_status TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            workload_id TEXT NOT NULL,
            left_p50_ms REAL,
            right_p50_ms REAL,
            delta_p50_percent REAL,
            comparable BOOLEAN,
            claimable BOOLEAN,
            FOREIGN KEY(run_id) REFERENCES runs(id)
        )
    ''')
    conn.commit()

def ingest_report(conn: sqlite3.Connection, report_path: Path):
    if not report_path.exists():
        logging.error(f"Report file not found: {report_path}")
        return False
        
    try:
        with report_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        logging.error(f"Failed to parse report JSON: {exc}")
        return False

    cursor = conn.cursor()
    
    # Insert run
    cursor.execute('''
        INSERT INTO runs (generated_at, schema_version, workload_contract_sha256, claim_status)
        VALUES (?, ?, ?, ?)
    ''', (
        data.get("generatedAt", ""),
        data.get("schemaVersion", 0),
        data.get("workloadContract", {}).get("sha256", ""),
        data.get("claimStatus", "unknown")
    ))
    
    run_id = cursor.lastrowid
    
    # Insert workloads
    workloads = data.get("workloads", [])
    for workload in workloads:
        left_stats = workload.get("left", {}).get("stats", {})
        right_stats = workload.get("right", {}).get("stats", {})
        delta = workload.get("deltaPercent", {})
        
        cursor.execute('''
            INSERT INTO workloads (
                run_id, workload_id, left_p50_ms, right_p50_ms, 
                delta_p50_percent, comparable, claimable
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            run_id,
            workload.get("id", ""),
            left_stats.get("p50Ms"),
            right_stats.get("p50Ms"),
            delta.get("p50Percent"),
            workload.get("comparability", {}).get("comparable", False),
            workload.get("claimability", {}).get("claimable", False)
        ))
        
    conn.commit()
    logging.info(f"Successfully ingested {len(workloads)} workloads from {report_path.name}")
    return True

def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    with sqlite3.connect(db_path) as conn:
        setup_database(conn)
        success = ingest_report(conn, Path(args.report))
        
    return 0 if success else 1
    
if __name__ == "__main__":
    sys.exit(main())
