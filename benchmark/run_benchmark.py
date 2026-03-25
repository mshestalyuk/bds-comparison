"""
Main benchmark entry point (expanded for 5.0 grade).

Usage:
    # Standard run (24 scenarios, 3 attempts)
    python -m benchmark.run_benchmark

    # Only specific databases
    python -m benchmark.run_benchmark --db postgres,mongo

    # Include denormalized schema comparison (H3 hypothesis)
    python -m benchmark.run_benchmark --db postgres --denorm

    # Run WITHOUT indexes first, then WITH indexes (comparison)
    python -m benchmark.run_benchmark --db postgres --index-compare

    # Run EXPLAIN analysis
    python -m benchmark.run_benchmark --db postgres --explain

    # Large dataset sizes for 5.0
    python -m benchmark.run_benchmark --size 500000,1000000,10000000

Results are saved to benchmark/results/
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
# Runner imports
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

    # Denormalized runners
    try:
        from benchmark.runners.postgres_denorm_runner import PostgresDenormRunner
        runners["postgres_denorm"] = PostgresDenormRunner
    except ImportError as e:
        print(f"[WARN] PostgreSQL denorm driver not available: {e}")

    return runners


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Database CRUD benchmark (24 scenarios)")
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
    p.add_argument(
        "--denorm",
        action="store_true",
        help="Also run denormalized schema benchmark (H3 hypothesis)",
    )
    p.add_argument(
        "--index-compare",
        action="store_true",
        help="Run benchmark twice: with and without indexes (H1 hypothesis)",
    )
    p.add_argument(
        "--explain",
        action="store_true",
        help="Run EXPLAIN ANALYZE on representative queries",
    )
    p.add_argument(
        "--scenarios",
        default=None,
        help="Comma-separated scenario IDs to run (default: all 24)",
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
    "index_mode",  # "with_indexes" or "without_indexes"
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
    """Pivot-style summary: scenario × db, one row per dataset size."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"summary_{timestamp}.csv")

    from collections import defaultdict
    table = defaultdict(dict)
    dbs_seen = []
    for r in rows:
        idx_mode = r.get("index_mode", "with_indexes")
        key = (r["scenario_id"], r["scenario_name"], r["operation"],
               r["dataset_size"], idx_mode)
        db = r["db"]
        table[key][db] = r["avg_ms"]
        if db not in dbs_seen:
            dbs_seen.append(db)

    headers = ["scenario_id", "scenario_name", "operation",
               "dataset_size", "index_mode"] + dbs_seen
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for (sid, sname, op, size, imode), db_times in sorted(table.items()):
            row = {
                "scenario_id":   sid,
                "scenario_name": sname,
                "operation":     op,
                "dataset_size":  size,
                "index_mode":    imode,
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


def run_benchmark(selected_dbs: list, sizes: list, attempts: int,
                  index_mode: str = "with_indexes",
                  scenario_filter: list = None) -> list:
    all_runners = _load_runners()
    results     = []
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")

    scenarios = SCENARIOS
    if scenario_filter:
        scenarios = [s for s in SCENARIOS if s["id"] in scenario_filter]

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
            print(f"  {db_name.upper():18s} | {dataset_size:>12,} records | {index_mode}")
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

            # ---- Drop indexes if requested ----------------------------
            if index_mode == "without_indexes" and hasattr(runner, 'drop_extra_indexes'):
                print(f"  [indexes] dropping non-PK indexes...")
                runner.drop_extra_indexes()

            # ---- Scenarios --------------------------------------------
            for scenario in scenarios:
                sid      = scenario["id"]
                sname    = scenario["name"]
                ops_cnt  = SCENARIO_OPS.get(sid, 1)
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
                        traceback.print_exc()
                        attempt_times.append(None)
                        continue

                    if t_ms == 0.0:
                        # Scenario not applicable for this runner
                        print(f"    attempt {attempt}: N/A (skipped)")
                        attempt_times.append(None)
                        continue

                    attempt_times.append(t_ms)
                    ops_per_sec = (ops_cnt / t_ms * 1_000) if t_ms > 0 else 0
                    print(
                        f"    attempt {attempt}: {t_ms:10.2f} ms  "
                        f"({ops_per_sec:>10.1f} ops/s)"
                    )

                valid = [t for t in attempt_times if t is not None]
                if not valid:
                    continue

                avg_ms = sum(valid) / len(valid)
                ops_s  = ops_cnt / avg_ms * 1_000 if avg_ms > 0 else 0

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
                    "index_mode":    index_mode,
                }
                results.append(row)

                print(
                    f"  → avg {avg_ms:.2f} ms | "
                    f"min {min(valid):.2f} | max {max(valid):.2f} | "
                    f"{ops_s:.1f} ops/s"
                )

            # ---- Restore indexes if dropped ---------------------------
            if index_mode == "without_indexes" and hasattr(runner, 'create_extra_indexes'):
                print(f"\n  [indexes] recreating indexes...")
                runner.create_extra_indexes()

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
    args         = parse_args()
    sel_dbs      = [d.strip() for d in args.db.split(",")]
    sel_sizes    = [int(s.strip()) for s in args.size.split(",")]
    sel_attempts = args.attempts
    sel_scenarios = None
    if args.scenarios:
        sel_scenarios = [s.strip().upper() for s in args.scenarios.split(",")]

    # Add denorm runners if requested
    if args.denorm:
        extra = []
        for db in sel_dbs:
            denorm_name = f"{db}_denorm"
            if denorm_name not in sel_dbs:
                extra.append(denorm_name)
        sel_dbs.extend(extra)

    print(f"\nBenchmark configuration:")
    print(f"  Databases : {sel_dbs}")
    print(f"  Sizes     : {sel_sizes}")
    print(f"  Attempts  : {sel_attempts} per scenario")
    print(f"  Scenarios : {len(sel_scenarios) if sel_scenarios else len(SCENARIOS)} total")
    if args.index_compare:
        print(f"  Mode      : Index comparison (WITH + WITHOUT)")
    if args.denorm:
        print(f"  Mode      : Including denormalized schema (H3 hypothesis)")
    print()

    all_results = []

    if args.index_compare:
        # Run twice: with and without indexes
        print("\n" + "=" * 70)
        print("  PHASE 1: WITH INDEXES")
        print("=" * 70)
        r1 = run_benchmark(sel_dbs, sel_sizes, sel_attempts,
                           index_mode="with_indexes",
                           scenario_filter=sel_scenarios)
        all_results.extend(r1)

        print("\n" + "=" * 70)
        print("  PHASE 2: WITHOUT INDEXES")
        print("=" * 70)
        r2 = run_benchmark(sel_dbs, sel_sizes, sel_attempts,
                           index_mode="without_indexes",
                           scenario_filter=sel_scenarios)
        all_results.extend(r2)

        # Save combined
        if all_results:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            p1 = save_results(all_results, f"index_compare_{ts}")
            p2 = save_summary(all_results, f"index_compare_{ts}")
            print(f"\n  Combined index comparison saved:")
            print(f"    detail  → {p1}")
            print(f"    summary → {p2}")
    else:
        run_benchmark(sel_dbs, sel_sizes, sel_attempts,
                      scenario_filter=sel_scenarios)

    # Run EXPLAIN if requested
    if args.explain:
        print("\n" + "=" * 70)
        print("  EXPLAIN ANALYZE")
        print("=" * 70)
        from benchmark.explain_analyzer import main as explain_main
        explain_main()
