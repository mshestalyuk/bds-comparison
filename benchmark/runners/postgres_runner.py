"""
PostgreSQL benchmark runner — implements all 24 scenarios.

New scenarios vs original 12:
  C4 — Insert with JSONB metadata
  C5 — Concurrent inserts (4 threads)
  C6 — Upsert via ON CONFLICT
  R4 — JOIN employee + contract + evaluation
  R5 — LIKE / pattern search on name
  R6 — Paginated listing ORDER BY + LIMIT/OFFSET
  U4 — Update JSONB field
  U5 — Concurrent salary updates (4 threads)
  U6 — Multi-table transactional update
  D4 — Delete by JSONB condition
  D5 — Bulk delete by hire_date range
  D6 — Concurrent deletes (4 threads)
"""
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import psycopg2
import psycopg2.extras

from benchmark.config import CONNECTIONS, BATCH_SIZE
from benchmark.generate import (
    chunked, contract_for, employee_generator, evaluation_for, pool_employee,
)
from benchmark.runners.base_runner import BaseRunner

_INIT_SQL = os.path.join(os.path.dirname(__file__), "..", "..", "postgres-init.sql")

EMP_COLS = (
    "first_name", "last_name", "pesel", "email", "phone",
    "date_of_birth", "hire_date", "position", "department_id",
    "salary_gross", "status", "address_street", "address_city", "address_zip",
)
# Extended columns including metadata JSONB
EMP_COLS_META = EMP_COLS + ("metadata",)

CON_COLS = (
    "employee_id", "contract_type", "start_date", "end_date",
    "working_hours", "probation_end", "status",
)
EVAL_COLS = (
    "employee_id", "evaluator_id", "period", "eval_date",
    "score_technical", "score_leadership", "score_communication",
    "score_teamwork", "score_initiative", "overall", "comments", "recommendation",
)


def _row(d: dict, cols: tuple) -> tuple:
    return tuple(d[c] for c in cols)


class PostgresRunner(BaseRunner):

    @property
    def name(self) -> str:
        return "postgres"

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self):
        cfg = CONNECTIONS["postgres"]
        self._conn = psycopg2.connect(**cfg)
        self._conn.autocommit = False
        self._cur = self._conn.cursor()

    def _new_conn(self):
        """Create a new independent connection (for concurrent scenarios)."""
        cfg = CONNECTIONS["postgres"]
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        return conn

    def _exec(self, sql: str, params=None):
        self._cur.execute(sql, params)

    def _commit(self):
        self._conn.commit()

    def _rollback(self):
        self._conn.rollback()

    # ------------------------------------------------------------------
    # EXPLAIN support
    # ------------------------------------------------------------------

    def explain(self, sql: str, params=None) -> str:
        """Run EXPLAIN ANALYZE on a query and return the plan as text."""
        self._cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}", params)
        rows = self._cur.fetchall()
        self._conn.rollback()   # don't commit side effects
        return "\n".join(r[0] for r in rows)

    # ------------------------------------------------------------------
    # Index toggle (for before/after index comparison)
    # ------------------------------------------------------------------

    def drop_extra_indexes(self):
        """Drop non-PK, non-UNIQUE indexes for before/after comparison."""
        self._conn.autocommit = True
        for idx_name in [
            "idx_employees_department", "idx_employees_status",
            "idx_employees_salary", "idx_employees_name",
            "idx_employees_hire_date",
            "idx_contracts_employee", "idx_contracts_status",
            "idx_contracts_end_date",
            "idx_leave_employee_date", "idx_evaluations_employee",
        ]:
            try:
                self._cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
            except Exception:
                pass
        self._conn.autocommit = False

    def create_extra_indexes(self):
        """Recreate indexes after no-index benchmark run."""
        from benchmark.config import INDEXES_TO_TOGGLE
        self._conn.autocommit = True
        for sql in INDEXES_TO_TOGGLE.get("postgres", []):
            try:
                self._cur.execute(sql)
            except Exception:
                pass
        self._conn.autocommit = False

    # ------------------------------------------------------------------
    # setup / teardown
    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()

        with open(_INIT_SQL, encoding="utf-8") as f:
            sql = f.read()
        self._conn.autocommit = True
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    self._cur.execute(stmt)
                except Exception:
                    pass
        self._conn.autocommit = False

        # Ensure metadata column exists (JSONB)
        self._conn.autocommit = True
        try:
            self._cur.execute(
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'"
            )
        except Exception:
            pass
        # GIN index on JSONB
        try:
            self._cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_employees_metadata "
                "ON employees USING GIN (metadata)"
            )
        except Exception:
            pass
        self._conn.autocommit = False

        # Clear sample data
        self._exec("""
            TRUNCATE TABLE evaluations, training_participants, trainings,
                           leave_requests, contracts, employees
            RESTART IDENTITY CASCADE
        """)
        self._commit()

        # Employees in batches (with metadata)
        emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS_META)}) VALUES %s"
        gen = employee_generator(n, with_metadata=True)
        for batch in chunked(gen, BATCH_SIZE):
            rows = []
            for e in batch:
                r = list(_row(e, EMP_COLS))
                r.append(json.dumps(e.get("metadata", {}), ensure_ascii=False))
                rows.append(tuple(r))
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
        self._commit()

        # Contracts
        con_sql = f"INSERT INTO contracts ({', '.join(CON_COLS)}) VALUES %s"
        self._exec("SELECT id FROM employees ORDER BY id")
        emp_ids = [r[0] for r in self._cur.fetchall()]

        for batch_ids in chunked(enumerate(emp_ids), BATCH_SIZE):
            rows = [_row(contract_for(eid, i), CON_COLS) for i, eid in batch_ids]
            psycopg2.extras.execute_values(self._cur, con_sql, rows, page_size=BATCH_SIZE)
        self._commit()

        # Evaluations for a sample (needed for R4 JOINs)
        eval_sql = f"INSERT INTO evaluations ({', '.join(EVAL_COLS)}) VALUES %s"
        sample_for_eval = random.sample(emp_ids, min(5_000, n))
        eval_rows = []
        for eid in sample_for_eval:
            ev = evaluation_for(eid, emp_ids[0], f"2024-H2")
            eval_rows.append(_row(ev, EVAL_COLS))
        for batch in chunked(eval_rows, BATCH_SIZE):
            psycopg2.extras.execute_values(self._cur, eval_sql, batch, page_size=BATCH_SIZE)
        self._commit()

        self._sample_ids = random.sample(emp_ids, min(2_000, n))
        self._emp_ids_all = emp_ids
        self._evaluator_id = emp_ids[0]

    def teardown(self) -> None:
        try:
            self._exec("""
                TRUNCATE TABLE evaluations, training_participants, trainings,
                               leave_requests, contracts, employees
                RESTART IDENTITY CASCADE
            """)
            self._commit()
        finally:
            self._cur.close()
            self._conn.close()

    # ------------------------------------------------------------------
    # before / after scenario
    # ------------------------------------------------------------------

    def before_scenario(self, scenario_id: str) -> None:
        self._pool_ids = []

        if scenario_id == "C1":
            self._c_pool = [pool_employee("c1", i) for i in range(100)]
        elif scenario_id == "C2":
            self._c_pool = [pool_employee("c2", i) for i in range(10_000)]
        elif scenario_id == "C3":
            self._c_pool = [pool_employee("c3", i) for i in range(50)]
        elif scenario_id == "C4":
            self._c_pool = [pool_employee("c4", i, with_metadata=True) for i in range(500)]
        elif scenario_id == "C5":
            self._c_pool = [pool_employee("c5", i) for i in range(1_000)]
        elif scenario_id == "C6":
            # Prepare 500 employees: first 250 already exist, last 250 are new
            existing = [pool_employee("c6", i) for i in range(250)]
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, EMP_COLS) for e in existing]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            self._commit()
            # Full pool: 250 existing (will be updated) + 250 new
            new = [pool_employee("c6", i + 250) for i in range(250)]
            self._c_pool = existing + new

        elif scenario_id in ("D1", "D2", "D3"):
            count  = 500 if scenario_id in ("D1", "D2") else 50
            tag    = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pool   = [pool_employee(tag, i, status=status) for i in range(count)]
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, EMP_COLS) for e in pool]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            if scenario_id == "D3":
                con_sql = f"INSERT INTO contracts ({', '.join(CON_COLS)}) VALUES %s"
                c_rows = [_row(contract_for(eid, i), CON_COLS)
                          for i, eid in enumerate(self._pool_ids)]
                psycopg2.extras.execute_values(self._cur, con_sql, c_rows, page_size=BATCH_SIZE)
            self._commit()

        elif scenario_id == "D4":
            # 100 employees with metadata containing {"remote_eligible": true}
            pool = [pool_employee("d4", i, with_metadata=True) for i in range(100)]
            for p in pool:
                p["metadata"]["remote_eligible"] = True  # ensure condition matches
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS_META)}) VALUES %s RETURNING id"
            rows = []
            for e in pool:
                r = list(_row(e, EMP_COLS))
                r.append(json.dumps(e["metadata"], ensure_ascii=False))
                rows.append(tuple(r))
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            self._commit()

        elif scenario_id == "D5":
            # 500 employees with old hire_date
            pool = [pool_employee("d5", i) for i in range(500)]
            for p in pool:
                p["hire_date"] = "2016-01-01"
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, EMP_COLS) for e in pool]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            self._commit()

        elif scenario_id == "D6":
            pool = [pool_employee("d6", i) for i in range(500)]
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, EMP_COLS) for e in pool]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            self._commit()

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C3", "C4", "C5", "C6"):
            tag = scenario_id.lower()
            self._exec(
                f"DELETE FROM employees WHERE email LIKE 'pool_{tag}_%@bench.test'"
            )
            self._commit()
        elif self._pool_ids:
            ids = self._pool_ids
            self._exec("DELETE FROM employees WHERE id = ANY(%s)", (ids,))
            self._commit()
            self._pool_ids = []

    # ------------------------------------------------------------------
    # Scenario dispatch
    # ------------------------------------------------------------------

    def run_scenario(self, scenario_id: str) -> float:
        fn = getattr(self, f"_run_{scenario_id.lower()}")
        return fn()

    # ---- CREATE ----

    def _run_c1(self) -> float:
        emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES ({', '.join(['%s']*len(EMP_COLS))})"
        t0 = self._now_ms()
        for e in self._c_pool:
            self._exec(emp_sql, _row(e, EMP_COLS))
        self._commit()
        return self._now_ms() - t0

    def _run_c2(self) -> float:
        emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s"
        t0 = self._now_ms()
        for batch in chunked(iter(self._c_pool), BATCH_SIZE):
            rows = [_row(e, EMP_COLS) for e in batch]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
        self._commit()
        return self._now_ms() - t0

    def _run_c3(self) -> float:
        emp_sql = (
            f"INSERT INTO employees ({', '.join(EMP_COLS)}) "
            f"VALUES ({', '.join(['%s']*len(EMP_COLS))}) RETURNING id"
        )
        con_sql = (
            f"INSERT INTO contracts ({', '.join(CON_COLS)}) "
            f"VALUES ({', '.join(['%s']*len(CON_COLS))})"
        )
        eval_sql = (
            f"INSERT INTO evaluations ({', '.join(EVAL_COLS)}) "
            f"VALUES ({', '.join(['%s']*len(EVAL_COLS))})"
        )
        t0 = self._now_ms()
        for i, e in enumerate(self._c_pool):
            try:
                self._exec(emp_sql, _row(e, EMP_COLS))
                eid = self._cur.fetchone()[0]
                self._exec(con_sql, _row(contract_for(eid, i), CON_COLS))
                ev = evaluation_for(eid, self._evaluator_id, f"BENCH-C3-{i}")
                self._exec(eval_sql, _row(ev, EVAL_COLS))
                self._commit()
            except Exception:
                self._rollback()
        return self._now_ms() - t0

    def _run_c4(self) -> float:
        """Insert employees with JSONB metadata."""
        emp_sql = (
            f"INSERT INTO employees ({', '.join(EMP_COLS_META)}) "
            f"VALUES ({', '.join(['%s']*len(EMP_COLS_META))})"
        )
        t0 = self._now_ms()
        for e in self._c_pool:
            r = list(_row(e, EMP_COLS))
            r.append(json.dumps(e.get("metadata", {}), ensure_ascii=False))
            self._exec(emp_sql, tuple(r))
        self._commit()
        return self._now_ms() - t0

    def _run_c5(self) -> float:
        """Concurrent inserts from 4 threads."""
        chunks = list(chunked(self._c_pool, len(self._c_pool) // 4 + 1))

        def _worker(pool_chunk):
            conn = self._new_conn()
            cur = conn.cursor()
            sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES ({', '.join(['%s']*len(EMP_COLS))})"
            for e in pool_chunk:
                cur.execute(sql, _row(e, EMP_COLS))
            conn.commit()
            cur.close()
            conn.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_c6(self) -> float:
        """Upsert: INSERT ... ON CONFLICT (email) DO UPDATE."""
        sql = (
            f"INSERT INTO employees ({', '.join(EMP_COLS)}) "
            f"VALUES ({', '.join(['%s']*len(EMP_COLS))}) "
            f"ON CONFLICT (email) DO UPDATE SET "
            f"salary_gross = EXCLUDED.salary_gross, status = EXCLUDED.status"
        )
        t0 = self._now_ms()
        for e in self._c_pool:
            self._exec(sql, _row(e, EMP_COLS))
        self._commit()
        return self._now_ms() - t0

    # ---- READ ----

    def _run_r1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0 = self._now_ms()
        for eid in ids:
            self._exec("SELECT * FROM employees WHERE id = %s", (eid,))
            self._cur.fetchone()
        return self._now_ms() - t0

    def _run_r2(self) -> float:
        t0 = self._now_ms()
        for _ in range(100):
            dept = random.randint(1, 5)
            lo   = random.uniform(3_500, 10_000)
            hi   = lo + random.uniform(5_000, 15_000)
            self._exec(
                "SELECT * FROM employees "
                "WHERE department_id = %s AND salary_gross BETWEEN %s AND %s",
                (dept, lo, hi),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r3(self) -> float:
        t0 = self._now_ms()
        for _ in range(10):
            self._exec(
                "SELECT department_id, COUNT(*), AVG(salary_gross), "
                "MIN(salary_gross), MAX(salary_gross) "
                "FROM employees GROUP BY department_id"
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r4(self) -> float:
        """JOIN: employee + latest contract + latest evaluation."""
        ids = random.choices(self._sample_ids, k=500)
        sql = """
            SELECT e.*, c.contract_type, c.start_date, c.end_date, c.status AS con_status,
                   ev.overall, ev.recommendation
            FROM employees e
            LEFT JOIN contracts c ON c.employee_id = e.id
            LEFT JOIN evaluations ev ON ev.employee_id = e.id
            WHERE e.id = %s
            ORDER BY c.start_date DESC, ev.eval_date DESC
            LIMIT 1
        """
        t0 = self._now_ms()
        for eid in ids:
            self._exec(sql, (eid,))
            self._cur.fetchone()
        return self._now_ms() - t0

    def _run_r5(self) -> float:
        """Pattern search on last_name."""
        patterns = ["Kow%", "Now%", "Wis%", "Ziel%", "Lew%",
                     "%ski", "%ska", "%icz", "%owski", "%ewski"]
        t0 = self._now_ms()
        for _ in range(200):
            pat = random.choice(patterns)
            self._exec(
                "SELECT * FROM employees WHERE last_name LIKE %s LIMIT 50",
                (pat,),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r6(self) -> float:
        """Paginated listing."""
        page_size = 50
        t0 = self._now_ms()
        for page in range(100):
            offset = page * page_size
            self._exec(
                "SELECT * FROM employees ORDER BY last_name, first_name "
                "LIMIT %s OFFSET %s",
                (page_size, offset),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    # ---- UPDATE ----

    def _run_u1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0 = self._now_ms()
        for eid in ids:
            new_salary = round(random.uniform(3_500, 25_000), 2)
            self._exec(
                "UPDATE employees SET salary_gross = %s WHERE id = %s",
                (new_salary, eid),
            )
        self._commit()
        return self._now_ms() - t0

    def _run_u2(self) -> float:
        t0 = self._now_ms()
        for dept_id in range(1, 6):
            self._exec(
                "UPDATE employees SET salary_gross = ROUND(salary_gross * 1.1, 2) "
                "WHERE department_id = %s",
                (dept_id,),
            )
        self._commit()
        return self._now_ms() - t0

    def _run_u3(self) -> float:
        today = date.today().isoformat()
        t0 = self._now_ms()
        self._exec(
            "UPDATE contracts SET status = 'expired' "
            "WHERE end_date < %s AND status = 'active'",
            (today,),
        )
        self._commit()
        return self._now_ms() - t0

    def _run_u4(self) -> float:
        """Update JSONB metadata — set a new key."""
        ids = random.choices(self._sample_ids, k=500)
        t0 = self._now_ms()
        for eid in ids:
            new_note = f"Updated at benchmark run {random.randint(1, 999)}"
            self._exec(
                "UPDATE employees SET metadata = jsonb_set("
                "  COALESCE(metadata, '{}'), '{notes}', %s::jsonb"
                ") WHERE id = %s",
                (json.dumps(new_note), eid),
            )
        self._commit()
        return self._now_ms() - t0

    def _run_u5(self) -> float:
        """Concurrent salary updates from 4 threads (disjoint ID sets)."""
        # Use a large enough sample, then split into non-overlapping chunks
        pool = random.sample(self._emp_ids_all, min(1_000, len(self._emp_ids_all)))
        # Sort to avoid deadlocks from lock ordering
        pool.sort()
        chunk_size = len(pool) // 4
        chunks = [
            pool[i * chunk_size:(i + 1) * chunk_size] for i in range(4)
        ]

        def _worker(id_chunk):
            conn = self._new_conn()
            cur = conn.cursor()
            for eid in id_chunk:
                new_salary = round(random.uniform(3_500, 25_000), 2)
                cur.execute(
                    "UPDATE employees SET salary_gross = %s WHERE id = %s",
                    (new_salary, eid),
                )
            conn.commit()
            cur.close()
            conn.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_u6(self) -> float:
        """Multi-table update: employee status + contract status in one TX."""
        ids = random.choices(self._sample_ids, k=200)
        t0 = self._now_ms()
        for eid in ids:
            self._exec(
                "UPDATE employees SET status = 'on_leave' WHERE id = %s", (eid,)
            )
            self._exec(
                "UPDATE contracts SET status = 'suspended' "
                "WHERE employee_id = %s AND status = 'active'", (eid,)
            )
        self._commit()
        return self._now_ms() - t0

    # ---- DELETE ----

    def _run_d1(self) -> float:
        t0 = self._now_ms()
        for eid in self._pool_ids:
            self._exec("DELETE FROM employees WHERE id = %s", (eid,))
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d2(self) -> float:
        t0 = self._now_ms()
        self._exec(
            "DELETE FROM employees "
            "WHERE status = 'terminated' AND email LIKE 'pool_d2_%@bench.test'"
        )
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d3(self) -> float:
        t0 = self._now_ms()
        for eid in self._pool_ids:
            self._exec("DELETE FROM employees WHERE id = %s", (eid,))
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d4(self) -> float:
        """Delete employees where JSONB metadata->remote_eligible = true."""
        t0 = self._now_ms()
        self._exec(
            "DELETE FROM employees "
            "WHERE metadata->>'remote_eligible' = 'true' "
            "AND email LIKE 'pool_d4_%@bench.test'"
        )
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d5(self) -> float:
        """Bulk delete by hire_date range."""
        t0 = self._now_ms()
        self._exec(
            "DELETE FROM employees "
            "WHERE hire_date < '2017-01-01' AND email LIKE 'pool_d5_%@bench.test'"
        )
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d6(self) -> float:
        """Concurrent deletes from 4 threads."""
        chunks = list(chunked(self._pool_ids, len(self._pool_ids) // 4 + 1))

        def _worker(id_chunk):
            conn = self._new_conn()
            cur = conn.cursor()
            for eid in id_chunk:
                cur.execute("DELETE FROM employees WHERE id = %s", (eid,))
            conn.commit()
            cur.close()
            conn.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        self._pool_ids = []
        return self._now_ms() - t0
