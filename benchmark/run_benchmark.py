"""
Main benchmark entry point.

Usage:
    cd <repo-root>
    python -m benchmark.run_benchmark [--db postgres,mysql,mongo,redis] [--size 10000,100000,1000000]

Results are saved to benchmark/results/benchmark_<timestamp>.csv
"""
import argparse
import csv
import os
import sys
import time
import traceback
from datetime import datetime

from benchmark.config import (
    ATTEMPTS, DATASET_SIZES, RUNNER_MAX_DATASET, SCENARIO_OPS, SCENARIOS,
)

# ---------------------------------------------------------------------------
# Runner imports — catch missing driver gracefully
# ---------------------------------------------------------------------------

def _load_runners():
    runners = {}
    try:
        from benchmark.runners.postgres_runner import PostgresRunner
        runners["postgres"] = PostgresRunner
    except ImportError as e:
        print(f"[WARN] PostgreSQL driver not available: {e}")

    try:
        from benchmark.runners.mysql_runner import MySQLRunner
        runners["mysql"] = MySQLRunner
    except ImportError as e:
        print(f"[WARN] MySQL driver not available: {e}")

    try:
        from benchmark.runners.mongo_runner import MongoRunner
        runners["mongo"] = MongoRunner
    except ImportError as e:
        print(f"[WARN] MongoDB driver not available: {e}")

    try:
        from benchmark.runners.redis_runner import RedisRunner
        runners["redis"] = RedisRunner
    except ImportError as e:
        print(f"[WARN] Redis driver not available: {e}")

    return runners


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Database CRUD benchmark")
    p.add_argument(
        "--db",
        default="postgres,mysql,mongo,redis",
        help="Comma-separated list of databases to benchmark",
    )
    p.add_argument(
        "--size",
        default=",".join(str(s) for s in DATASET_SIZES),
        help="Comma-separated dataset sizes",
    )
    p.add_argument(
        "--attempts",
        type=int,
        default=ATTEMPTS,
        help=f"Number of attempts per scenario (default {ATTEMPTS})",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

CSV_FIELDS = [
    "db", "scenario_id", "scenario_name", "operation", "dataset_size",
    "attempt_1_ms", "attempt_2_ms", "attempt_3_ms",
    "avg_ms", "min_ms", "max_ms",
    "ops_count", "avg_ops_per_sec",
]


def save_results(rows: list, timestamp: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"benchmark_{timestamp}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def save_summary(rows: list, timestamp: str) -> str:
    """Save a pivot-style summary: scenario × db, one row per dataset size."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"summary_{timestamp}.csv")

    # Group: (scenario_id, dataset_size) → {db: avg_ms}
    from collections import defaultdict
    table = defaultdict(dict)
    dbs_seen = []
    for r in rows:
        key = (r["scenario_id"], r["scenario_name"], r["operation"], r["dataset_size"])
        db  = r["db"]
        table[key][db] = r["avg_ms"]
        if db not in dbs_seen:
            dbs_seen.append(db)

    headers = ["scenario_id", "scenario_name", "operation", "dataset_size"] + dbs_seen
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for (sid, sname, op, size), db_times in sorted(table.items()):
            row = {
                "scenario_id":   sid,
                "scenario_name": sname,
                "operation":     op,
                "dataset_size":  size,
            }
            for db in dbs_seen:
                row[db] = db_times.get(db, "")
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SEP  = "=" * 68
SEP2 = "-" * 68


def run_benchmark(selected_dbs: list, sizes: list, attempts: int) -> list:
    all_runners = _load_runners()
    results     = []
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")

    for db_name in selected_dbs:
        if db_name not in all_runners:
            print(f"\n[SKIP] No runner for '{db_name}'")
            continue

        RunnerClass = all_runners[db_name]
        runner      = RunnerClass()

        for dataset_size in sizes:
            max_size = RUNNER_MAX_DATASET.get(db_name, 1_000_000)
            if dataset_size > max_size:
                print(
                    f"\n[SKIP] {db_name.upper()} | {dataset_size:,} records "
                    f"exceeds max ({max_size:,})"
                )
                continue

            print(f"\n{SEP}")
            print(f"  {db_name.upper():10s} | {dataset_size:>12,} records")
            print(SEP)

            # ---- Setup ------------------------------------------------
            print(f"  [setup] loading {dataset_size:,} records ...", end="", flush=True)
            t_setup = time.perf_counter()
            try:
                runner.setup(dataset_size)
            except Exception as exc:
                msg = str(exc) or repr(exc)
                print(f"\n  [ERROR] setup failed: {msg}")
                traceback.print_exc()
                continue
            print(f" done ({time.perf_counter() - t_setup:.1f}s)")

            # ---- Scenarios --------------------------------------------
            for scenario in SCENARIOS:
                sid      = scenario["id"]
                sname    = scenario["name"]
                ops_cnt  = SCENARIO_OPS[sid]
                attempt_times = []

                print(f"\n  {sid} — {sname}")
                print(f"  {SEP2}")

                for attempt in range(1, attempts + 1):
                    try:
                        runner.before_scenario(sid)
                        t_ms = runner.run_scenario(sid)
                        runner.after_scenario(sid)
                    except Exception as exc:
                        print(f"    attempt {attempt}: ERROR — {exc}")
                        attempt_times.append(None)
                        continue

                    attempt_times.append(t_ms)
                    ops_per_sec = (ops_cnt / t_ms * 1_000) if t_ms > 0 else 0
                    print(
                        f"    attempt {attempt}: {t_ms:10.2f} ms  "
                        f"({ops_per_sec:>10.1f} ops/s)"
                    )

                # Filter out failed attempts
                valid = [t for t in attempt_times if t is not None]
                if not valid:
                    continue

                avg_ms = sum(valid) / len(valid)
                ops_s  = ops_cnt / avg_ms * 1_000 if avg_ms > 0 else 0

                # Pad to exactly `attempts` slots
                padded = attempt_times + [None] * (attempts - len(attempt_times))
                row = {
                    "db":            db_name,
                    "scenario_id":   sid,
                    "scenario_name": sname,
                    "operation":     scenario["operation"],
                    "dataset_size":  dataset_size,
                    "attempt_1_ms":  _fmt(padded[0]),
                    "attempt_2_ms":  _fmt(padded[1]) if attempts >= 2 else "",
                    "attempt_3_ms":  _fmt(padded[2]) if attempts >= 3 else "",
                    "avg_ms":        round(avg_ms, 3),
                    "min_ms":        round(min(valid), 3),
                    "max_ms":        round(max(valid), 3),
                    "ops_count":     ops_cnt,
                    "avg_ops_per_sec": round(ops_s, 1),
                }
                results.append(row)

                print(
                    f"  → avg {avg_ms:.2f} ms | "
                    f"min {min(valid):.2f} | max {max(valid):.2f} | "
                    f"{ops_s:.1f} ops/s"
                )

            # ---- Teardown ---------------------------------------------
            print(f"\n  [teardown] ...", end="", flush=True)
            try:
                runner.teardown()
                print(" done")
            except Exception as exc:
                print(f" ERROR: {exc}")

    # ---- Save results -------------------------------------------------
    if results:
        detail_path  = save_results(results, timestamp)
        summary_path = save_summary(results, timestamp)
        print(f"\n{SEP}")
        print(f"  Results saved:")
        print(f"    detail  → {detail_path}")
        print(f"    summary → {summary_path}")
        print(SEP)
    else:
        print("\n[WARN] No results collected.")

    return results


def _fmt(v):
    return round(v, 3) if v is not None else ""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args        = parse_args()
    sel_dbs     = [d.strip() for d in args.db.split(",")]
    sel_sizes   = [int(s.strip()) for s in args.size.split(",")]
    sel_attempts = args.attempts

    print(f"\nBenchmark configuration:")
    print(f"  Databases : {sel_dbs}")
    print(f"  Sizes     : {sel_sizes}")
    print(f"  Attempts  : {sel_attempts} per scenario")
    print(f"  Scenarios : {len(SCENARIOS)} total\n")

    run_benchmark(sel_dbs, sel_sizes, sel_attempts)
