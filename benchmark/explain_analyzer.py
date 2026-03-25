"""
EXPLAIN plan analyzer for PostgreSQL and MySQL.

Runs representative queries with and without indexes,
captures EXPLAIN ANALYZE output, and saves comparison.

Usage:
    python -m benchmark.explain_analyzer [--db postgres|mysql] [--size 100000]
"""
import argparse
import csv
import os
from datetime import datetime

import psycopg2

from benchmark.config import CONNECTIONS, INDEXES_TO_TOGGLE

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Representative queries to EXPLAIN
QUERIES_POSTGRES = [
    {
        "name": "R1 — PK Lookup",
        "sql": "SELECT * FROM employees WHERE id = 1",
        "params": None,
    },
    {
        "name": "R2 — Filtered by dept + salary",
        "sql": "SELECT * FROM employees WHERE department_id = 1 AND salary_gross BETWEEN 5000 AND 15000",
        "params": None,
    },
    {
        "name": "R3 — Aggregation GROUP BY",
        "sql": "SELECT department_id, COUNT(*), AVG(salary_gross) FROM employees GROUP BY department_id",
        "params": None,
    },
    {
        "name": "R4 — JOIN employee + contract + evaluation",
        "sql": (
            "SELECT e.*, c.contract_type, c.status AS con_status, ev.overall "
            "FROM employees e "
            "LEFT JOIN contracts c ON c.employee_id = e.id "
            "LEFT JOIN evaluations ev ON ev.employee_id = e.id "
            "WHERE e.id = 1"
        ),
        "params": None,
    },
    {
        "name": "R5 — LIKE pattern search",
        "sql": "SELECT * FROM employees WHERE last_name LIKE 'Kow%' LIMIT 50",
        "params": None,
    },
    {
        "name": "R6 — Pagination ORDER BY + OFFSET",
        "sql": "SELECT * FROM employees ORDER BY last_name, first_name LIMIT 50 OFFSET 1000",
        "params": None,
    },
    {
        "name": "U3 — Conditional update (contracts)",
        "sql": "UPDATE contracts SET status = 'expired' WHERE end_date < '2025-01-01' AND status = 'active'",
        "params": None,
    },
    {
        "name": "D2 — Conditional delete",
        "sql": "DELETE FROM employees WHERE status = 'terminated' AND email LIKE 'pool_d2_%@bench.test'",
        "params": None,
    },
]


def run_explain(conn, sql, params=None):
    """Run EXPLAIN ANALYZE and return plan text. Rolls back to avoid side effects."""
    cur = conn.cursor()
    try:
        cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}", params)
        rows = cur.fetchall()
        return "\n".join(r[0] for r in rows)
    except Exception as e:
        return f"ERROR: {e}"
    finally:
        conn.rollback()


def drop_indexes(conn):
    """Drop non-PK indexes."""
    conn.autocommit = True
    cur = conn.cursor()
    for idx in INDEXES_TO_TOGGLE.get("postgres", []):
        idx_name = idx.split("INDEX")[-1].split("ON")[0].strip()
        idx_name = idx_name.replace("IF NOT EXISTS ", "")
        try:
            cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
        except Exception:
            pass
    conn.autocommit = False


def create_indexes(conn):
    """Recreate indexes."""
    conn.autocommit = True
    cur = conn.cursor()
    for sql in INDEXES_TO_TOGGLE.get("postgres", []):
        try:
            cur.execute(sql.replace("CREATE INDEX", "CREATE INDEX IF NOT EXISTS"))
        except Exception:
            pass
    conn.autocommit = False


def main():
    parser = argparse.ArgumentParser(description="EXPLAIN plan analyzer")
    parser.add_argument("--db", default="postgres")
    args = parser.parse_args()

    cfg = CONNECTIONS[args.db]
    conn = psycopg2.connect(**cfg)
    conn.autocommit = False

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    outpath = os.path.join(RESULTS_DIR, f"explain_{args.db}_{timestamp}.txt")

    results = []

    # Phase 1: WITH indexes
    print("=== Phase 1: WITH indexes ===")
    create_indexes(conn)
    for q in QUERIES_POSTGRES:
        print(f"  EXPLAIN: {q['name']}")
        plan = run_explain(conn, q["sql"], q["params"])
        results.append({
            "query": q["name"],
            "phase": "WITH indexes",
            "plan": plan,
        })

    # Phase 2: WITHOUT indexes
    print("\n=== Phase 2: WITHOUT indexes ===")
    drop_indexes(conn)
    for q in QUERIES_POSTGRES:
        print(f"  EXPLAIN: {q['name']}")
        plan = run_explain(conn, q["sql"], q["params"])
        results.append({
            "query": q["name"],
            "phase": "WITHOUT indexes",
            "plan": plan,
        })

    # Restore indexes
    create_indexes(conn)
    conn.close()

    # Save results
    with open(outpath, "w", encoding="utf-8") as f:
        for r in results:
            f.write(f"\n{'='*70}\n")
            f.write(f"Query: {r['query']}\n")
            f.write(f"Phase: {r['phase']}\n")
            f.write(f"{'='*70}\n")
            f.write(r["plan"])
            f.write("\n")

    print(f"\nResults saved to: {outpath}")


if __name__ == "__main__":
    main()
