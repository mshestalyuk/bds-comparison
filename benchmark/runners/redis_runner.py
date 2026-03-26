"""
Redis benchmark runner — implements all 24 scenarios.

Key schema:
  employee:{id}          Hash  — profile fields + metadata JSON string
  dept:{CODE}:members    Set   — employee IDs per department
  salary:ranking         ZSet  — score=salary, member="employee:{id}"
  contract:{id}          Hash  — contract fields
  eval:{id}              Hash  — evaluation fields

Pool keys: bench_{tag}_{i}
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import redis as redis_lib

from benchmark.config import CONNECTIONS, BATCH_SIZE, RUNNER_MAX_DATASET
from benchmark.generate import (
    chunked, employee_generator, pool_employee, _generate_metadata,
)
from benchmark.runners.base_runner import BaseRunner

DEPT_CODES = {1: "IT", 2: "HR", 3: "FIN", 4: "MKT", 5: "LOG"}
ID_OFFSET  = 1_000


class RedisRunner(BaseRunner):

    @property
    def name(self) -> str:
        return "redis"

    @property
    def max_dataset_size(self) -> int:
        return RUNNER_MAX_DATASET["redis"]

    def _connect(self):
        cfg = CONNECTIONS["redis"]
        self._r = redis_lib.Redis(
            host=cfg["host"], port=cfg["port"],
            password=cfg["password"], decode_responses=True,
        )

    def _new_redis(self):
        cfg = CONNECTIONS["redis"]
        return redis_lib.Redis(
            host=cfg["host"], port=cfg["port"],
            password=cfg["password"], decode_responses=True,
        )

    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()
        self._r.flushdb()

        pipe = self._r.pipeline(transaction=False)
        gen  = employee_generator(n, offset=0, with_metadata=True)
        count = 0

        for batch in chunked(gen, BATCH_SIZE):
            for i, emp in enumerate(batch):
                idx       = ID_OFFSET + count + i
                key       = f"employee:{idx}"
                dept_code = DEPT_CODES[emp["department_id"]]
                pipe.hset(key, mapping={
                    "first_name":  emp["first_name"],
                    "last_name":   emp["last_name"],
                    "email":       emp["email"],
                    "position":    emp["position"],
                    "department":  dept_code,
                    "salary":      emp["salary_gross"],
                    "status":      emp["status"],
                    "hire_date":   emp["hire_date"],
                    "metadata":    json.dumps(emp.get("metadata", {}), ensure_ascii=False),
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
                # evaluation
                scores = [random.randint(1, 5) for _ in range(5)]
                pipe.hset(f"eval:{idx}", mapping={
                    "employee_id": idx,
                    "overall": round(sum(scores) / 5, 1),
                    "recommendation": random.choice(["awans", "podwyżka", "szkolenie"]),
                })
            pipe.execute()
            count += len(batch)

        self._all_ids    = list(range(ID_OFFSET, ID_OFFSET + n))
        self._sample_ids = random.sample(self._all_ids, min(2_000, n))

    def teardown(self) -> None:
        self._r.flushdb()
        self._r.close()

    # ------------------------------------------------------------------

    def before_scenario(self, scenario_id: str) -> None:
        self._pool_keys = []
        self._pool_ids  = []

        if scenario_id in ("C1", "C2", "C3", "C4", "C5", "C6"):
            count = {
                "C1": 100, "C2": 10_000, "C3": 50,
                "C4": 500, "C5": 1_000, "C6": 500,
            }[scenario_id]
            tag = scenario_id.lower()
            self._c_pool_tag   = tag
            self._c_pool_count = count

            if scenario_id == "C6":
                # Pre-insert 250 (existing) for upsert test
                pipe = self._r.pipeline(transaction=False)
                for i in range(250):
                    k = f"bench_{tag}_{i}"
                    pipe.hset(k, mapping={
                        "first_name": "Bench", "last_name": f"Pool{i}",
                        "email": f"pool_{tag}_{i}@bench.test",
                        "salary": "5000", "status": "active", "department": "IT",
                    })
                pipe.execute()

        elif scenario_id in ("D1", "D2", "D3", "D4", "D5", "D6"):
            count_map = {"D1": 500, "D2": 500, "D3": 50, "D4": 100, "D5": 500, "D6": 500}
            count = count_map[scenario_id]
            tag   = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pipe  = self._r.pipeline(transaction=False)
            keys  = []
            for i in range(count):
                k = f"bench_{tag}_{i}"
                mapping = {
                    "first_name": "Bench",
                    "last_name":  f"Pool{i}",
                    "email":      f"pool_{tag}_{i}@bench.test",
                    "salary":     "5000",
                    "status":     status,
                    "department": "IT",
                    "hire_date":  "2016-01-01" if scenario_id == "D5" else "2020-01-01",
                }
                if scenario_id == "D4":
                    mapping["metadata"] = json.dumps({"remote_eligible": True})
                pipe.hset(k, mapping=mapping)
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
        if scenario_id in ("C1", "C2", "C3", "C4", "C5", "C6"):
            tag = self._c_pool_tag
            count = self._c_pool_count
            pipe = self._r.pipeline(transaction=False)
            for i in range(count):
                pipe.delete(f"bench_{tag}_{i}")
                pipe.delete(f"bench_{tag}_con_{i}")
            pipe.execute()
        elif self._pool_keys:
            pipe = self._r.pipeline(transaction=False)
            for k in self._pool_keys:
                pipe.delete(k)
            # Also clean up D3 contract keys
            for i in range(len(self._pool_keys)):
                pipe.delete(f"bench_d3_con_{i}")
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
        """Transactional: HSET employee + HSET contract (MULTI/EXEC)."""
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

    def _run_c4(self) -> float:
        """Insert with JSON metadata."""
        tag   = self._c_pool_tag
        count = self._c_pool_count
        t0    = self._now_ms()
        for i in range(count):
            meta = json.dumps(_generate_metadata(), ensure_ascii=False)
            self._r.hset(f"bench_{tag}_{i}", mapping={
                "first_name": "Bench", "last_name": f"Pool{i}",
                "email": f"pool_{tag}_{i}@bench.test",
                "salary": "5000", "status": "active", "department": "IT",
                "metadata": meta,
            })
        return self._now_ms() - t0

    def _run_c5(self) -> float:
        """Concurrent inserts from 4 threads."""
        tag   = self._c_pool_tag
        count = self._c_pool_count
        chunk_size = count // 4
        ranges = [(i * chunk_size, (i + 1) * chunk_size) for i in range(4)]

        def _worker(start, end):
            r = self._new_redis()
            for i in range(start, end):
                r.hset(f"bench_{tag}_{i}", mapping={
                    "first_name": "Bench", "last_name": f"Pool{i}",
                    "email": f"pool_{tag}_{i}@bench.test",
                    "salary": "5000", "status": "active", "department": "IT",
                })
            r.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, s, e) for s, e in ranges]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_c6(self) -> float:
        """Upsert: HSET on existing and new keys (Redis HSET is always upsert)."""
        tag   = self._c_pool_tag
        count = self._c_pool_count
        t0    = self._now_ms()
        for i in range(count):
            self._r.hset(f"bench_{tag}_{i}", mapping={
                "first_name": "Bench", "last_name": f"Pool{i}",
                "email": f"pool_{tag}_{i}@bench.test",
                "salary": str(round(random.uniform(4000, 12000), 2)),
                "status": "active", "department": "IT",
            })
        return self._now_ms() - t0

    # ---- READ ----

    def _run_r1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        t0  = self._now_ms()
        for idx in ids:
            self._r.hgetall(f"employee:{idx}")
        return self._now_ms() - t0

    def _run_r2(self) -> float:
        """Filter by department + salary range."""
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
                [s for s in salaries if s and lo <= float(s) <= hi]
        return self._now_ms() - t0

    def _run_r3(self) -> float:
        """AVG salary per department."""
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

    def _run_r4(self) -> float:
        """Lookup employee + contract + evaluation (pipeline)."""
        ids = random.choices(self._sample_ids, k=500)
        t0 = self._now_ms()
        for idx in ids:
            pipe = self._r.pipeline(transaction=False)
            pipe.hgetall(f"employee:{idx}")
            pipe.hgetall(f"contract:{idx}")
            pipe.hgetall(f"eval:{idx}")
            pipe.execute()
        return self._now_ms() - t0

    def _run_r5(self) -> float:
        """Pattern search on last_name via SCAN + pipeline HGET."""
        patterns = ["Kow", "Now", "Wis", "Ziel", "Lew"]
        t0 = self._now_ms()
        for _ in range(200):
            pat = random.choice(patterns)
            # SCAN all employee keys, check last_name
            found = 0
            cursor = 0
            while found < 50:
                cursor, keys = self._r.scan(cursor, match="employee:*", count=200)
                if keys:
                    pipe = self._r.pipeline(transaction=False)
                    for k in keys:
                        pipe.hget(k, "last_name")
                    names = pipe.execute()
                    for n in names:
                        if n and n.startswith(pat):
                            found += 1
                if cursor == 0:
                    break
        return self._now_ms() - t0

    def _run_r6(self) -> float:
        """Paginated listing via sorted set."""
        t0 = self._now_ms()
        page_size = 50
        for page in range(100):
            start = page * page_size
            end = start + page_size - 1
            members = self._r.zrange("salary:ranking", start, end)
            if members:
                pipe = self._r.pipeline(transaction=False)
                for m in members:
                    pipe.hgetall(m)
                pipe.execute()
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
        """Raise salary by 10% for all department members."""
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
        """Update contracts with past end_date."""
        today = date.today().isoformat()
        t0    = self._now_ms()
        cursor = 0
        pipe   = self._r.pipeline(transaction=False)
        while True:
            cursor, keys = self._r.scan(cursor, match="contract:*", count=500)
            for key in keys:
                end_date = self._r.hget(key, "end_date")
                status   = self._r.hget(key, "status")
                if end_date and status == "active" and end_date < today:
                    pipe.hset(key, "status", "expired")
            if cursor == 0:
                break
        pipe.execute()
        return self._now_ms() - t0

    def _run_u4(self) -> float:
        """Update JSON metadata field."""
        ids = random.choices(self._sample_ids, k=500)
        t0 = self._now_ms()
        for idx in ids:
            raw = self._r.hget(f"employee:{idx}", "metadata")
            if raw:
                try:
                    meta = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    meta = {}
            else:
                meta = {}
            meta["notes"] = f"Updated at benchmark run {random.randint(1, 999)}"
            self._r.hset(f"employee:{idx}", "metadata",
                         json.dumps(meta, ensure_ascii=False))
        return self._now_ms() - t0

    def _run_u5(self) -> float:
        """Concurrent salary updates (disjoint ID sets)."""
        pool = random.sample(self._all_ids, min(1_000, len(self._all_ids)))
        pool.sort()
        chunk_size = len(pool) // 4
        chunks = [pool[i * chunk_size:(i + 1) * chunk_size] for i in range(4)]

        def _worker(id_chunk):
            r = self._new_redis()
            for idx in id_chunk:
                new_salary = round(random.uniform(3_500, 25_000), 2)
                r.hset(f"employee:{idx}", "salary", new_salary)
            r.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_u6(self) -> float:
        """Update employee status + contract status."""
        ids = random.choices(self._sample_ids, k=200)
        t0 = self._now_ms()
        for idx in ids:
            with self._r.pipeline() as pipe:
                pipe.multi()
                pipe.hset(f"employee:{idx}", "status", "on_leave")
                pipe.hset(f"contract:{idx}", "status", "suspended")
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
        """Cascade delete: employee + contract + set/zset cleanup."""
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

    def _run_d4(self) -> float:
        """Delete by JSON metadata condition."""
        keys = self._pool_keys
        t0   = self._now_ms()
        pipe = self._r.pipeline(transaction=False)
        for k in keys:
            raw = self._r.hget(k, "metadata")
            if raw:
                try:
                    meta = json.loads(raw)
                    if meta.get("remote_eligible"):
                        pipe.delete(k)
                except (json.JSONDecodeError, TypeError):
                    pass
        pipe.execute()
        self._pool_keys = []
        return self._now_ms() - t0

    def _run_d5(self) -> float:
        """Bulk delete by hire_date."""
        keys = self._pool_keys
        t0   = self._now_ms()
        pipe = self._r.pipeline(transaction=False)
        for k in keys:
            hd = self._r.hget(k, "hire_date")
            if hd and hd < "2017-01-01":
                pipe.delete(k)
        pipe.execute()
        self._pool_keys = []
        return self._now_ms() - t0

    def _run_d6(self) -> float:
        """Concurrent deletes from 4 threads."""
        keys = self._pool_keys
        chunk_size = len(keys) // 4
        chunks = [keys[i * chunk_size:(i + 1) * chunk_size] for i in range(4)]
        remainder = keys[4 * chunk_size:]
        if remainder and chunks:
            chunks[-1] = chunks[-1] + remainder

        def _worker(key_chunk):
            r = self._new_redis()
            for k in key_chunk:
                r.delete(k)
            r.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        self._pool_keys = []
        return self._now_ms() - t0
