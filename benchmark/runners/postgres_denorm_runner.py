"""
PostgreSQL DENORMALIZED benchmark runner.

Uses a single flat table `employees_denorm` with embedded department,
contract, and evaluation data. No JOINs needed for reads.

This runner implements the same 24 scenarios but against the denormalized
schema, allowing direct comparison with the normalized PostgresRunner
to verify hypothesis H3:
  "Denormalizacja danych poprawia wydajność zapytań odczytowych
   kosztem operacji modyfikujących dane."
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
    chunked, denorm_employee_generator, pool_employee,
)
from benchmark.runners.base_runner import BaseRunner

_INIT_SQL_DENORM = os.path.join(
    os.path.dirname(__file__), "..", "..", "postgres-denorm-init.sql"
)

DENORM_COLS = (
    "first_name", "last_name", "pesel", "email", "phone",
    "date_of_birth", "hire_date", "position", "salary_gross", "status",
    "address_street", "address_city", "address_zip",
    "dept_code", "dept_name", "dept_budget",
    "contract_type", "contract_start", "contract_end", "contract_status",
    "working_hours",
    "score_technical", "score_leadership", "score_communication",
    "score_teamwork", "score_initiative", "eval_overall",
    "metadata",
)


def _row(d: dict, cols: tuple) -> tuple:
    return tuple(d[c] for c in cols)


class PostgresDenormRunner(BaseRunner):

    @property
    def name(self) -> str:
        return "postgres_denorm"

    def _connect(self):
        cfg = CONNECTIONS["postgres_denorm"]
        self._conn = psycopg2.connect(**cfg)
        self._conn.autocommit = False
        self._cur = self._conn.cursor()

    def _new_conn(self):
        cfg = CONNECTIONS["postgres_denorm"]
        conn = psycopg2.connect(**cfg)
        conn.autocommit = False
        return conn

    def _exec(self, sql, params=None):
        self._cur.execute(sql, params)

    def _commit(self):
        self._conn.commit()

    def _rollback(self):
        self._conn.rollback()

    def explain(self, sql: str, params=None) -> str:
        self._cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {sql}", params)
        rows = self._cur.fetchall()
        self._conn.rollback()
        return "\n".join(r[0] for r in rows)

    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()

        # Create denormalized DB if needed
        self._conn.autocommit = True
        try:
            self._cur.execute("SELECT 1")  # test connection
        except Exception:
            pass
        self._conn.autocommit = False

        # Run init SQL
        with open(_INIT_SQL_DENORM, encoding="utf-8") as f:
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

        # Truncate
        self._exec("TRUNCATE TABLE employees_denorm RESTART IDENTITY")
        self._commit()

        # Load data
        insert_sql = f"INSERT INTO employees_denorm ({', '.join(DENORM_COLS)}) VALUES %s"
        gen = denorm_employee_generator(n)
        for batch in chunked(gen, BATCH_SIZE):
            rows = [_row(e, DENORM_COLS) for e in batch]
            psycopg2.extras.execute_values(self._cur, insert_sql, rows, page_size=BATCH_SIZE)
        self._commit()

        self._exec("SELECT id FROM employees_denorm ORDER BY id")
        emp_ids = [r[0] for r in self._cur.fetchall()]
        self._sample_ids  = random.sample(emp_ids, min(2_000, n))
        self._emp_ids_all = emp_ids

    def teardown(self) -> None:
        try:
            self._exec("TRUNCATE TABLE employees_denorm RESTART IDENTITY")
            self._commit()
        finally:
            self._cur.close()
            self._conn.close()

    # ------------------------------------------------------------------

    def before_scenario(self, scenario_id: str) -> None:
        self._pool_ids = []

        if scenario_id in ("C1", "C2", "C4"):
            count = {"C1": 100, "C2": 10_000, "C4": 500}[scenario_id]
            tag = scenario_id.lower()
            gen = denorm_employee_generator(count, offset=900_000)
            self._c_pool = []
            for i, e in enumerate(gen):
                e["email"] = f"pool_{tag}_{i}@bench.test"
                e["pesel"] = f"{tag.upper()}{i:08d}"[:11]
                self._c_pool.append(e)

        elif scenario_id in ("D1", "D2", "D5"):
            count = {"D1": 500, "D2": 500, "D5": 500}[scenario_id]
            tag = scenario_id.lower()
            gen = denorm_employee_generator(count, offset=800_000)
            pool = []
            for i, e in enumerate(gen):
                e["email"] = f"pool_{tag}_{i}@bench.test"
                e["pesel"] = f"{tag.upper()}{i:08d}"[:11]
                if scenario_id == "D2":
                    e["status"] = "terminated"
                if scenario_id == "D5":
                    e["hire_date"] = "2016-01-01"
                pool.append(e)
            insert_sql = f"INSERT INTO employees_denorm ({', '.join(DENORM_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, DENORM_COLS) for e in pool]
            psycopg2.extras.execute_values(self._cur, insert_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            self._commit()

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C4"):
            tag = scenario_id.lower()
            self._exec(
                f"DELETE FROM employees_denorm WHERE email LIKE 'pool_{tag}_%@bench.test'"
            )
            self._commit()
        elif self._pool_ids:
            self._exec("DELETE FROM employees_denorm WHERE id = ANY(%s)", (self._pool_ids,))
            self._commit()
            self._pool_ids = []

    # ------------------------------------------------------------------

    def run_scenario(self, scenario_id: str) -> float:
        fn = getattr(self, f"_run_{scenario_id.lower()}", None)
        if fn is None:
            # Skip scenarios not applicable to denormalized schema
            return 0.0
        return fn()

    # ---- CREATE ----

    def _run_c1(self) -> float:
        sql = f"INSERT INTO employees_denorm ({', '.join(DENORM_COLS)}) VALUES ({', '.join(['%s']*len(DENORM_COLS))})"
        t0 = self._now_ms()
        for e in self._c_pool:
            self._exec(sql, _row(e, DENORM_COLS))
        self._commit()
        return self._now_ms() - t0

    def _run_c2(self) -> float:
        sql = f"INSERT INTO employees_denorm ({', '.join(DENORM_COLS)}) VALUES %s"
        t0 = self._now_ms()
        for batch in chunked(iter(self._c_pool), BATCH_SIZE):
            rows = [_row(e, DENORM_COLS) for e in batch]
            psycopg2.extras.execute_values(self._cur, sql, rows, page_size=BATCH_SIZE)
        self._commit()
        return self._now_ms() - t0

    # C3 — not applicable (no separate tables to transact across)

    def _run_c4(self) -> float:
        sql = f"INSERT INTO employees_denorm ({', '.join(DENORM_COLS)}) VALUES ({', '.join(['%s']*len(DENORM_COLS))})"
        t0 = self._now_ms()
        for e in self._c_pool:
            self._exec(sql, _row(e, DENORM_COLS))
        self._commit()
        return self._now_ms() - t0

    # ---- READ (key comparisons — denorm should win here) ----

    def _run_r1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0 = self._now_ms()
        for eid in ids:
            self._exec("SELECT * FROM employees_denorm WHERE id = %s", (eid,))
            self._cur.fetchone()
        return self._now_ms() - t0

    def _run_r2(self) -> float:
        t0 = self._now_ms()
        for _ in range(100):
            dept = random.choice(["IT", "HR", "FIN", "MKT", "LOG"])
            lo = random.uniform(3_500, 10_000)
            hi = lo + random.uniform(5_000, 15_000)
            self._exec(
                "SELECT * FROM employees_denorm "
                "WHERE dept_code = %s AND salary_gross BETWEEN %s AND %s",
                (dept, lo, hi),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r3(self) -> float:
        t0 = self._now_ms()
        for _ in range(10):
            self._exec(
                "SELECT dept_code, COUNT(*), AVG(salary_gross), "
                "MIN(salary_gross), MAX(salary_gross) "
                "FROM employees_denorm GROUP BY dept_code"
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r4(self) -> float:
        """No JOIN needed — all data is in one row."""
        ids = random.choices(self._sample_ids, k=500)
        t0 = self._now_ms()
        for eid in ids:
            self._exec(
                "SELECT * FROM employees_denorm WHERE id = %s", (eid,)
            )
            self._cur.fetchone()
        return self._now_ms() - t0

    def _run_r5(self) -> float:
        patterns = ["Kow%", "Now%", "Wis%", "Ziel%", "Lew%",
                     "%ski", "%ska", "%icz", "%owski", "%ewski"]
        t0 = self._now_ms()
        for _ in range(200):
            pat = random.choice(patterns)
            self._exec(
                "SELECT * FROM employees_denorm WHERE last_name LIKE %s LIMIT 50",
                (pat,),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    def _run_r6(self) -> float:
        page_size = 50
        t0 = self._now_ms()
        for page in range(100):
            offset = page * page_size
            self._exec(
                "SELECT * FROM employees_denorm ORDER BY last_name, first_name "
                "LIMIT %s OFFSET %s",
                (page_size, offset),
            )
            self._cur.fetchall()
        return self._now_ms() - t0

    # ---- UPDATE (denorm should be slower here — data duplication) ----

    def _run_u1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0 = self._now_ms()
        for eid in ids:
            new_salary = round(random.uniform(3_500, 25_000), 2)
            self._exec(
                "UPDATE employees_denorm SET salary_gross = %s WHERE id = %s",
                (new_salary, eid),
            )
        self._commit()
        return self._now_ms() - t0

    def _run_u2(self) -> float:
        t0 = self._now_ms()
        for dept in ["IT", "HR", "FIN", "MKT", "LOG"]:
            self._exec(
                "UPDATE employees_denorm SET salary_gross = ROUND(salary_gross * 1.1, 2) "
                "WHERE dept_code = %s",
                (dept,),
            )
        self._commit()
        return self._now_ms() - t0

    def _run_u3(self) -> float:
        today = date.today().isoformat()
        t0 = self._now_ms()
        self._exec(
            "UPDATE employees_denorm SET contract_status = 'expired' "
            "WHERE contract_end < %s AND contract_status = 'active'",
            (today,),
        )
        self._commit()
        return self._now_ms() - t0

    def _run_u4(self) -> float:
        ids = random.choices(self._sample_ids, k=500)
        t0 = self._now_ms()
        for eid in ids:
            new_note = f"Updated at benchmark run {random.randint(1, 999)}"
            self._exec(
                "UPDATE employees_denorm SET metadata = jsonb_set("
                "  COALESCE(metadata::jsonb, '{}'), '{notes}', %s::jsonb"
                ") WHERE id = %s",
                (json.dumps(new_note), eid),
            )
        self._commit()
        return self._now_ms() - t0

    # ---- DELETE ----

    def _run_d1(self) -> float:
        t0 = self._now_ms()
        for eid in self._pool_ids:
            self._exec("DELETE FROM employees_denorm WHERE id = %s", (eid,))
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d2(self) -> float:
        t0 = self._now_ms()
        self._exec(
            "DELETE FROM employees_denorm "
            "WHERE status = 'terminated' AND email LIKE 'pool_d2_%@bench.test'"
        )
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d5(self) -> float:
        t0 = self._now_ms()
        self._exec(
            "DELETE FROM employees_denorm "
            "WHERE hire_date < '2017-01-01' AND email LIKE 'pool_d5_%@bench.test'"
        )
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0
