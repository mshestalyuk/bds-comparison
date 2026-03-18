"""
Redis benchmark runner — implements all 12 scenarios.

Key schema used by benchmark:
  employee:{id}          Hash  — profile fields
  dept:{CODE}:members    Set   — employee IDs per department
  salary:ranking         ZSet  — score=salary, member="employee:{id}"
  contract:{id}          Hash  — contract fields

Pool keys (CREATE/DELETE scenarios use separate namespaces):
  bench_c1_{i}, bench_c2_{i}, bench_c3_{i}
  bench_d1_{i}, bench_d2_{i}, bench_d3_{i}  (employees)
  bench_d3_con_{i}                           (contracts for D3)
"""
import random
from datetime import date

import redis

from benchmark.config import CONNECTIONS, BATCH_SIZE, RUNNER_MAX_DATASET
from benchmark.generate import (
    chunked, employee_generator, pool_employee,
)
from benchmark.runners.base_runner import BaseRunner

DEPT_CODES = {1: "IT", 2: "HR", 3: "FIN", 4: "MKT", 5: "LOG"}
ID_OFFSET  = 1_000   # main employee IDs start here


class RedisRunner(BaseRunner):

    @property
    def name(self) -> str:
        return "redis"

    @property
    def max_dataset_size(self) -> int:
        return RUNNER_MAX_DATASET["redis"]

    def _connect(self):
        cfg = CONNECTIONS["redis"]
        self._r = redis.Redis(
            host=cfg["host"], port=cfg["port"],
            password=cfg["password"], decode_responses=True,
        )

    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()
        self._r.flushdb()

        pipe = self._r.pipeline(transaction=False)
        gen  = employee_generator(n, offset=0)
        count = 0

        for batch in chunked(gen, BATCH_SIZE):
            for i, emp in enumerate(batch):
                idx      = ID_OFFSET + count + i
                key      = f"employee:{idx}"
                dept_code = DEPT_CODES[emp["department_id"]]
                pipe.hset(key, mapping={
                    "first_name":  emp["first_name"],
                    "last_name":   emp["last_name"],
                    "email":       emp["email"],
                    "position":    emp["position"],
                    "department":  dept_code,
                    "salary":      emp["salary_gross"],
                    "status":      emp["status"],
                })
                pipe.sadd(f"dept:{dept_code}:members", idx)
                pipe.zadd("salary:ranking", {key: emp["salary_gross"]})
                # contract
                pipe.hset(f"contract:{idx}", mapping={
                    "employee_id":   idx,
                    "type":          random.choice(
                        ["umowa o pracę", "umowa zlecenie", "B2B"]),
                    "start_date":    "2020-01-01",
                    "end_date":      random.choice(["2023-12-31", "", "2026-12-31"]),
                    "status":        "active",
                })
            pipe.execute()
            count += len(batch)

        # Cache sample IDs
        self._all_ids   = list(range(ID_OFFSET, ID_OFFSET + n))
        self._sample_ids = random.sample(self._all_ids, min(2_000, n))

    def teardown(self) -> None:
        self._r.flushdb()
        self._r.close()

    # ------------------------------------------------------------------

    def before_scenario(self, scenario_id: str) -> None:
        self._pool_keys = []
        self._pool_ids  = []

        if scenario_id in ("C1", "C2", "C3"):
            count = {"C1": 100, "C2": 10_000, "C3": 50}[scenario_id]
            tag   = scenario_id.lower()
            self._c_pool_tag   = tag
            self._c_pool_count = count

        elif scenario_id in ("D1", "D2", "D3"):
            count  = 500 if scenario_id in ("D1", "D2") else 50
            tag    = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pipe   = self._r.pipeline(transaction=False)
            keys   = []
            for i in range(count):
                k = f"bench_{tag}_{i}"
                pipe.hset(k, mapping={
                    "first_name": "Bench",
                    "last_name":  f"Pool{i}",
                    "email":      f"pool_{tag}_{i}@bench.test",
                    "salary":     "5000",
                    "status":     status,
                    "department": "IT",
                })
                keys.append(k)
                if scenario_id == "D3":
                    ck = f"bench_d3_con_{i}"
                    pipe.hset(ck, mapping={
                        "employee_key": k,
                        "type":         "umowa o pracę",
                        "status":       "active",
                        "end_date":     "2022-12-31",
                    })
            pipe.execute()
            self._pool_keys = keys

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C3"):
            tag = self._c_pool_tag
            # delete any leftover pool keys
            pipe = self._r.pipeline(transaction=False)
            count = {"c1": 100, "c2": 10_000, "c3": 50}[tag]
            for i in range(count):
                pipe.delete(f"bench_{tag}_{i}")
            pipe.execute()
        elif self._pool_keys:
            pipe = self._r.pipeline(transaction=False)
            for k in self._pool_keys:
                pipe.delete(k)
            pipe.execute()
            self._pool_keys = []

    # ------------------------------------------------------------------

    def run_scenario(self, scenario_id: str) -> float:
        return getattr(self, f"_run_{scenario_id.lower()}")()

    # ---- CREATE ----

    def _run_c1(self) -> float:
        tag   = self._c_pool_tag
        count = self._c_pool_count
        t0    = self._now_ms()
        for i in range(count):
            self._r.hset(f"bench_{tag}_{i}", mapping={
                "first_name": "Bench", "last_name": f"Pool{i}",
                "email": f"pool_{tag}_{i}@bench.test",
                "salary": "5000", "status": "active", "department": "IT",
            })
        return self._now_ms() - t0

    def _run_c2(self) -> float:
        tag   = self._c_pool_tag
        count = self._c_pool_count
        pipe  = self._r.pipeline(transaction=False)
        t0    = self._now_ms()
        for i in range(count):
            pipe.hset(f"bench_{tag}_{i}", mapping={
                "first_name": "Bench", "last_name": f"Pool{i}",
                "email": f"pool_{tag}_{i}@bench.test",
                "salary": "5000", "status": "active", "department": "IT",
            })
            if (i + 1) % BATCH_SIZE == 0:
                pipe.execute()
                pipe = self._r.pipeline(transaction=False)
        pipe.execute()
        return self._now_ms() - t0

    def _run_c3(self) -> float:
        """Transactional: HSET employee + HSET contract (MULTI/EXEC per pair)."""
        tag   = self._c_pool_tag
        count = self._c_pool_count
        t0    = self._now_ms()
        for i in range(count):
            with self._r.pipeline() as pipe:
                pipe.multi()
                pipe.hset(f"bench_{tag}_{i}", mapping={
                    "first_name": "Bench", "last_name": f"Pool{i}",
                    "email": f"pool_{tag}_{i}@bench.test",
                    "salary": "5000", "status": "active", "department": "IT",
                })
                pipe.hset(f"bench_{tag}_con_{i}", mapping={
                    "employee_key": f"bench_{tag}_{i}",
                    "type": "umowa o pracę", "status": "active",
                    "score_avg": str(round(random.uniform(1, 5), 1)),
                })
                pipe.execute()
        return self._now_ms() - t0

    # ---- READ ----

    def _run_r1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0  = self._now_ms()
        for idx in ids:
            self._r.hgetall(f"employee:{idx}")
        return self._now_ms() - t0

    def _run_r2(self) -> float:
        """Filter by department + salary range via SMEMBERS + pipeline HGET."""
        dept_codes = list(DEPT_CODES.values())
        t0 = self._now_ms()
        for _ in range(100):
            code = random.choice(dept_codes)
            lo   = random.uniform(3_500, 10_000)
            hi   = lo + random.uniform(5_000, 15_000)
            members = self._r.smembers(f"dept:{code}:members")
            if members:
                pipe = self._r.pipeline(transaction=False)
                for mid in members:
                    pipe.hget(f"employee:{mid}", "salary")
                salaries = pipe.execute()
                # filter (simulate WHERE salary BETWEEN lo AND hi)
                [s for s in salaries if s and lo <= float(s) <= hi]
        return self._now_ms() - t0

    def _run_r3(self) -> float:
        """AVG salary per department using SMEMBERS + pipeline HGET salary."""
        codes = list(DEPT_CODES.values())
        t0 = self._now_ms()
        for _ in range(10):
            for code in codes:
                members = self._r.smembers(f"dept:{code}:members")
                if members:
                    pipe = self._r.pipeline(transaction=False)
                    for mid in members:
                        pipe.hget(f"employee:{mid}", "salary")
                    salaries = [float(s) for s in pipe.execute() if s]
                    if salaries:
                        _avg = sum(salaries) / len(salaries)
        return self._now_ms() - t0

    # ---- UPDATE ----

    def _run_u1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0  = self._now_ms()
        for idx in ids:
            new_salary = round(random.uniform(3_500, 25_000), 2)
            self._r.hset(f"employee:{idx}", "salary", new_salary)
        return self._now_ms() - t0

    def _run_u2(self) -> float:
        """Raise salary by 10% for all members in each department."""
        t0 = self._now_ms()
        for code in DEPT_CODES.values():
            members = self._r.smembers(f"dept:{code}:members")
            if not members:
                continue
            pipe = self._r.pipeline(transaction=False)
            for mid in members:
                current = self._r.hget(f"employee:{mid}", "salary")
                if current:
                    new_sal = round(float(current) * 1.1, 2)
                    pipe.hset(f"employee:{mid}", "salary", new_sal)
                    pipe.zadd("salary:ranking", {f"employee:{mid}": new_sal})
            pipe.execute()
        return self._now_ms() - t0

    def _run_u3(self) -> float:
        """Update contracts with past end_date and status=active → expired."""
        today = date.today().isoformat()
        t0    = self._now_ms()
        cursor = 0
        pipe   = self._r.pipeline(transaction=False)
        updated = 0
        while True:
            cursor, keys = self._r.scan(cursor, match="contract:*", count=500)
            for key in keys:
                end_date = self._r.hget(key, "end_date")
                status   = self._r.hget(key, "status")
                if end_date and status == "active" and end_date < today:
                    pipe.hset(key, "status", "expired")
                    updated += 1
            if cursor == 0:
                break
        pipe.execute()
        return self._now_ms() - t0

    # ---- DELETE ----

    def _run_d1(self) -> float:
        keys = self._pool_keys
        t0   = self._now_ms()
        for k in keys:
            self._r.delete(k)
        self._pool_keys = []
        return self._now_ms() - t0

    def _run_d2(self) -> float:
        """Delete all pool_d2 keys with status=terminated."""
        keys = self._pool_keys
        t0   = self._now_ms()
        pipe = self._r.pipeline(transaction=False)
        for k in keys:
            status = self._r.hget(k, "status")
            if status == "terminated":
                pipe.delete(k)
        pipe.execute()
        self._pool_keys = []
        return self._now_ms() - t0

    def _run_d3(self) -> float:
        """Cascade delete: employee hash + contract hash + set/zset cleanup."""
        keys = self._pool_keys
        t0   = self._now_ms()
        pipe = self._r.pipeline(transaction=False)
        for i, k in enumerate(keys):
            emp_dept = self._r.hget(k, "department") or "IT"
            pipe.delete(k)
            pipe.delete(f"bench_d3_con_{i}")
            pipe.srem(f"dept:{emp_dept}:members", k)
            pipe.zrem("salary:ranking", k)
        pipe.execute()
        self._pool_keys = []
        return self._now_ms() - t0
