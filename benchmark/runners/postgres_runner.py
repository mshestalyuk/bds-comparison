"""
PostgreSQL benchmark runner — implements all 12 scenarios.
"""
import os
import random
from datetime import date

import psycopg2
import psycopg2.extras

from benchmark.config import CONNECTIONS, BATCH_SIZE
from benchmark.generate import (
    chunked, contract_for, employee_generator, evaluation_for, pool_employee,
)
from benchmark.runners.base_runner import BaseRunner

# Path to the existing init SQL (repo root)
_INIT_SQL = os.path.join(os.path.dirname(__file__), "..", "..", "postgres-init.sql")

EMP_COLS = (
    "first_name", "last_name", "pesel", "email", "phone",
    "date_of_birth", "hire_date", "position", "department_id",
    "salary_gross", "status", "address_street", "address_city", "address_zip",
)
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

    def _exec(self, sql: str, params=None):
        self._cur.execute(sql, params)

    def _execmany(self, sql: str, rows):
        psycopg2.extras.execute_values(self._cur, sql, rows, page_size=BATCH_SIZE)

    def _commit(self):
        self._conn.commit()

    def _rollback(self):
        self._conn.rollback()

    # ------------------------------------------------------------------
    # setup / teardown
    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()

        # Run the existing init SQL (drops + recreates schema + inserts sample data)
        with open(_INIT_SQL, encoding="utf-8") as f:
            sql = f.read()
        # psycopg2 requires autocommit for multi-statement DDL blocks
        self._conn.autocommit = True
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    self._cur.execute(stmt)
                except Exception:
                    pass  # skip empty/comment-only chunks
        self._conn.autocommit = False

        # Clear sample data (keep departments — needed for FK references)
        self._exec("""
            TRUNCATE TABLE evaluations, training_participants, trainings,
                           leave_requests, contracts, employees
            RESTART IDENTITY CASCADE
        """)
        self._commit()

        # Employees in batches
        emp_sql = (
            f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s"
        )
        gen = employee_generator(n)
        for batch in chunked(gen, BATCH_SIZE):
            rows = [_row(e, EMP_COLS) for e in batch]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
        self._commit()

        # Contracts — fetch employee IDs first (sequential 1..n after reset)
        con_sql = f"INSERT INTO contracts ({', '.join(CON_COLS)}) VALUES %s"
        self._exec("SELECT id FROM employees ORDER BY id")
        emp_ids = [r[0] for r in self._cur.fetchall()]

        for batch_ids in chunked(enumerate(emp_ids), BATCH_SIZE):
            rows = [_row(contract_for(eid, i), CON_COLS) for i, eid in batch_ids]
            psycopg2.extras.execute_values(self._cur, con_sql, rows, page_size=BATCH_SIZE)
        self._commit()

        # Cache sample IDs for read/update scenarios
        self._sample_ids = random.sample(emp_ids, min(2_000, n))
        self._emp_ids_all = emp_ids
        self._evaluator_id = emp_ids[0]   # use first employee as default evaluator

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
            # Prepare 100 employee dicts (just stored, inserted during run)
            self._c_pool = [pool_employee("c1", i) for i in range(100)]

        elif scenario_id == "C2":
            # Prepare 10,000 employee dicts
            self._c_pool = [pool_employee("c2", i) for i in range(10_000)]

        elif scenario_id == "C3":
            # Prepare 50 employee dicts (each gets a contract + evaluation)
            self._c_pool = [pool_employee("c3", i) for i in range(50)]

        elif scenario_id in ("D1", "D2", "D3"):
            count = 500 if scenario_id in ("D1", "D2") else 50
            tag   = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pool  = [pool_employee(tag, i, status=status) for i in range(count)]
            emp_sql = f"INSERT INTO employees ({', '.join(EMP_COLS)}) VALUES %s RETURNING id"
            rows = [_row(e, EMP_COLS) for e in pool]
            psycopg2.extras.execute_values(self._cur, emp_sql, rows, page_size=BATCH_SIZE)
            self._pool_ids = [r[0] for r in self._cur.fetchall()]
            if scenario_id == "D3":
                # Also insert a contract per pool employee
                con_sql = f"INSERT INTO contracts ({', '.join(CON_COLS)}) VALUES %s"
                c_rows = [_row(contract_for(eid, i), CON_COLS)
                          for i, eid in enumerate(self._pool_ids)]
                psycopg2.extras.execute_values(self._cur, con_sql, c_rows, page_size=BATCH_SIZE)
            self._commit()

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C3"):
            tag = scenario_id.lower()
            self._exec(
                f"DELETE FROM employees WHERE email LIKE 'pool_{tag}_%@bench.test'"
            )
            self._commit()
        elif self._pool_ids:
            # Safety: clean up any leftover pool records (shouldn't be needed)
            ids = self._pool_ids
            self._exec(
                f"DELETE FROM employees WHERE id = ANY(%s)", (ids,)
            )
            self._commit()
            self._pool_ids = []

    # ------------------------------------------------------------------
    # Scenario implementations
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
        # CASCADE on FK handles contracts / leave_requests / evaluations
        t0 = self._now_ms()
        for eid in self._pool_ids:
            self._exec("DELETE FROM employees WHERE id = %s", (eid,))
        self._commit()
        self._pool_ids = []
        return self._now_ms() - t0
