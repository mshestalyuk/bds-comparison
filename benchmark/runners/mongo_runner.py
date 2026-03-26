"""
MongoDB benchmark runner — implements all 24 scenarios.
"""
import json
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

from pymongo import MongoClient, ASCENDING

from benchmark.config import CONNECTIONS, BATCH_SIZE
from benchmark.generate import (
    chunked, contract_for, employee_generator, evaluation_for, pool_employee,
    _generate_metadata,
)
from benchmark.runners.base_runner import BaseRunner

DEPT_DOCS = [
    {"code": "IT",  "name": "Dział IT",          "budget_yearly": 850000},
    {"code": "HR",  "name": "Dział Kadr i Płac", "budget_yearly": 420000},
    {"code": "FIN", "name": "Dział Finansów",     "budget_yearly": 560000},
    {"code": "MKT", "name": "Dział Marketingu",   "budget_yearly": 720000},
    {"code": "LOG", "name": "Dział Logistyki",    "budget_yearly": 380000},
]


class MongoRunner(BaseRunner):

    @property
    def name(self) -> str:
        return "mongo"

    def _connect(self):
        cfg = CONNECTIONS["mongo"]
        uri = (
            f"mongodb://{cfg['user']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['db']}?authSource=admin"
        )
        self._client = MongoClient(uri)
        self._db = self._client[cfg["db"]]

    def _new_client(self):
        cfg = CONNECTIONS["mongo"]
        uri = (
            f"mongodb://{cfg['user']}:{cfg['password']}"
            f"@{cfg['host']}:{cfg['port']}/{cfg['db']}?authSource=admin"
        )
        return MongoClient(uri)

    # ------------------------------------------------------------------

    def setup(self, n: int) -> None:
        self._n = n
        self._connect()

        # Drop all collections
        for col in ("evaluations", "training_participants", "trainings",
                    "leave_requests", "contracts", "employees", "departments"):
            self._db[col].drop()

        # Departments
        self._db.departments.insert_many(DEPT_DOCS)

        # Employees (with metadata)
        emp_col = self._db.employees
        all_ids = []
        gen = employee_generator(n, with_metadata=True)
        for batch in chunked(gen, BATCH_SIZE):
            result = emp_col.insert_many(batch)
            all_ids.extend(result.inserted_ids)

        # Indexes
        emp_col.create_index("email", unique=True)
        emp_col.create_index("department_id")
        emp_col.create_index("status")
        emp_col.create_index("salary_gross")
        emp_col.create_index([("last_name", ASCENDING), ("first_name", ASCENDING)])
        emp_col.create_index("hire_date")

        # Contracts
        con_col = self._db.contracts
        for batch_ids in chunked(enumerate(all_ids), BATCH_SIZE):
            docs = [contract_for_mongo(eid, i) for i, eid in batch_ids]
            con_col.insert_many(docs)
        con_col.create_index("employee_id")
        con_col.create_index("status")
        con_col.create_index("end_date")

        # Evaluations for a sample
        eval_col = self._db.evaluations
        sample_for_eval = random.sample(all_ids, min(5_000, n))
        eval_docs = []
        for eid in sample_for_eval:
            ev = evaluation_for(str(eid), str(all_ids[0]), "2024-H2")
            ev["employee_id"] = eid
            ev["evaluator_id"] = all_ids[0]
            eval_docs.append(ev)
        for batch in chunked(eval_docs, BATCH_SIZE):
            eval_col.insert_many(batch)
        eval_col.create_index([("employee_id", ASCENDING), ("period", ASCENDING)])

        self._all_ids = all_ids
        self._sample_ids = random.sample(all_ids, min(2_000, n))
        self._evaluator_id = all_ids[0]

    def teardown(self) -> None:
        for col in ("evaluations", "training_participants", "trainings",
                    "leave_requests", "contracts", "employees", "departments"):
            self._db[col].drop()
        self._client.close()

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
            # 250 existing + 250 new
            existing = [pool_employee("c6", i) for i in range(250)]
            result = self._db.employees.insert_many(existing)
            self._pool_ids = list(result.inserted_ids)
            new = [pool_employee("c6", i + 250) for i in range(250)]
            self._c_pool = existing + new

        elif scenario_id in ("D1", "D2", "D3"):
            count  = 500 if scenario_id in ("D1", "D2") else 50
            tag    = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pool   = [pool_employee(tag, i, status=status) for i in range(count)]
            result = self._db.employees.insert_many(pool)
            self._pool_ids = list(result.inserted_ids)
            if scenario_id == "D3":
                cons = [contract_for_mongo(eid, i) for i, eid in enumerate(self._pool_ids)]
                self._db.contracts.insert_many(cons)

        elif scenario_id == "D4":
            pool = [pool_employee("d4", i, with_metadata=True) for i in range(100)]
            for p in pool:
                p["metadata"]["remote_eligible"] = True
            result = self._db.employees.insert_many(pool)
            self._pool_ids = list(result.inserted_ids)

        elif scenario_id == "D5":
            pool = [pool_employee("d5", i) for i in range(500)]
            for p in pool:
                p["hire_date"] = "2016-01-01"
            result = self._db.employees.insert_many(pool)
            self._pool_ids = list(result.inserted_ids)

        elif scenario_id == "D6":
            pool = [pool_employee("d6", i) for i in range(500)]
            result = self._db.employees.insert_many(pool)
            self._pool_ids = list(result.inserted_ids)

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C3", "C4", "C5", "C6"):
            tag = scenario_id.lower()
            self._db.employees.delete_many({"email": {"$regex": f"^pool_{tag}_"}})
        elif self._pool_ids:
            self._db.employees.delete_many({"_id": {"$in": self._pool_ids}})
            self._pool_ids = []

    # ------------------------------------------------------------------

    def run_scenario(self, scenario_id: str) -> float:
        return getattr(self, f"_run_{scenario_id.lower()}")()

    # ---- CREATE ----

    def _run_c1(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        for doc in self._c_pool:
            col.insert_one(doc)
        return self._now_ms() - t0

    def _run_c2(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        for batch in chunked(iter(self._c_pool), BATCH_SIZE):
            col.insert_many(batch)
        return self._now_ms() - t0

    def _run_c3(self) -> float:
        emp_col = self._db.employees
        con_col = self._db.contracts
        eval_col = self._db.evaluations
        t0 = self._now_ms()
        with self._client.start_session() as session:
            for i, doc in enumerate(self._c_pool):
                try:
                    with session.start_transaction():
                        res = emp_col.insert_one(doc, session=session)
                        eid = res.inserted_id
                        con_col.insert_one(
                            contract_for_mongo(eid, i), session=session
                        )
                        ev = evaluation_for(
                            str(eid), str(self._evaluator_id), f"BENCH-C3-{i}"
                        )
                        ev["employee_id"] = eid
                        ev["evaluator_id"] = self._evaluator_id
                        eval_col.insert_one(ev, session=session)
                except Exception:
                    pass
        return self._now_ms() - t0

    def _run_c4(self) -> float:
        """Insert with embedded metadata."""
        col = self._db.employees
        t0 = self._now_ms()
        for doc in self._c_pool:
            col.insert_one(doc)
        return self._now_ms() - t0

    def _run_c5(self) -> float:
        """Concurrent inserts from 4 threads."""
        chunks = list(chunked(self._c_pool, len(self._c_pool) // 4 + 1))

        def _worker(pool_chunk):
            client = self._new_client()
            db = client[CONNECTIONS["mongo"]["db"]]
            for doc in pool_chunk:
                db.employees.insert_one(doc)
            client.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_c6(self) -> float:
        """Upsert: update_one with upsert=True."""
        col = self._db.employees
        t0 = self._now_ms()
        for doc in self._c_pool:
            col.update_one(
                {"email": doc["email"]},
                {"$set": doc},
                upsert=True,
            )
        return self._now_ms() - t0

    # ---- READ ----

    def _run_r1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        col = self._db.employees
        t0 = self._now_ms()
        for eid in ids:
            col.find_one({"_id": eid})
        return self._now_ms() - t0

    def _run_r2(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        for _ in range(100):
            dept = random.randint(1, 5)
            lo   = random.uniform(3_500, 10_000)
            hi   = lo + random.uniform(5_000, 15_000)
            list(col.find({
                "department_id": dept,
                "salary_gross": {"$gte": lo, "$lte": hi},
            }))
        return self._now_ms() - t0

    def _run_r3(self) -> float:
        col = self._db.employees
        pipeline = [
            {"$group": {
                "_id": "$department_id",
                "count":      {"$sum": 1},
                "avg_salary": {"$avg": "$salary_gross"},
                "min_salary": {"$min": "$salary_gross"},
                "max_salary": {"$max": "$salary_gross"},
            }}
        ]
        t0 = self._now_ms()
        for _ in range(10):
            list(col.aggregate(pipeline))
        return self._now_ms() - t0

    def _run_r4(self) -> float:
        """$lookup — JOIN equivalent."""
        ids = random.choices(self._sample_ids, k=500)
        col = self._db.employees
        t0 = self._now_ms()
        for eid in ids:
            list(col.aggregate([
                {"$match": {"_id": eid}},
                {"$lookup": {
                    "from": "contracts",
                    "localField": "_id",
                    "foreignField": "employee_id",
                    "as": "contracts",
                }},
                {"$lookup": {
                    "from": "evaluations",
                    "localField": "_id",
                    "foreignField": "employee_id",
                    "as": "evaluations",
                }},
                {"$limit": 1},
            ]))
        return self._now_ms() - t0

    def _run_r5(self) -> float:
        """Regex search on last_name."""
        import re
        patterns = ["^Kow", "^Now", "^Wis", "^Ziel", "^Lew",
                     "ski$", "ska$", "icz$", "owski$", "ewski$"]
        col = self._db.employees
        t0 = self._now_ms()
        for _ in range(200):
            pat = random.choice(patterns)
            list(col.find({"last_name": {"$regex": pat}}).limit(50))
        return self._now_ms() - t0

    def _run_r6(self) -> float:
        """Paginated listing with sort + skip + limit."""
        col = self._db.employees
        page_size = 50
        t0 = self._now_ms()
        for page in range(100):
            offset = page * page_size
            list(col.find().sort([
                ("last_name", ASCENDING), ("first_name", ASCENDING)
            ]).skip(offset).limit(page_size))
        return self._now_ms() - t0

    # ---- UPDATE ----

    def _run_u1(self) -> float:
        ids = random.choices(self._sample_ids, k=1_000)
        col = self._db.employees
        t0 = self._now_ms()
        for eid in ids:
            new_salary = round(random.uniform(3_500, 25_000), 2)
            col.update_one({"_id": eid}, {"$set": {"salary_gross": new_salary}})
        return self._now_ms() - t0

    def _run_u2(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        for dept_id in range(1, 6):
            col.update_many(
                {"department_id": dept_id},
                {"$mul": {"salary_gross": 1.1}},
            )
        return self._now_ms() - t0

    def _run_u3(self) -> float:
        today = datetime.combine(date.today(), datetime.min.time())
        col = self._db.contracts
        t0 = self._now_ms()
        col.update_many(
            {"end_date": {"$lt": today.isoformat()}, "status": "active"},
            {"$set": {"status": "expired"}},
        )
        return self._now_ms() - t0

    def _run_u4(self) -> float:
        """Update nested metadata field."""
        ids = random.choices(self._sample_ids, k=500)
        col = self._db.employees
        t0 = self._now_ms()
        for eid in ids:
            new_note = f"Updated at benchmark run {random.randint(1, 999)}"
            col.update_one(
                {"_id": eid},
                {"$set": {"metadata.notes": new_note}},
            )
        return self._now_ms() - t0

    def _run_u5(self) -> float:
        """Concurrent updates (disjoint ID sets)."""
        pool = random.sample(self._all_ids, min(1_000, len(self._all_ids)))
        chunk_size = len(pool) // 4
        chunks = [pool[i * chunk_size:(i + 1) * chunk_size] for i in range(4)]

        def _worker(id_chunk):
            client = self._new_client()
            db = client[CONNECTIONS["mongo"]["db"]]
            for eid in id_chunk:
                new_salary = round(random.uniform(3_500, 25_000), 2)
                db.employees.update_one(
                    {"_id": eid}, {"$set": {"salary_gross": new_salary}}
                )
            client.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        return self._now_ms() - t0

    def _run_u6(self) -> float:
        """Multi-collection update: employee status + contract status."""
        ids = random.choices(self._sample_ids, k=200)
        emp_col = self._db.employees
        con_col = self._db.contracts
        t0 = self._now_ms()
        for eid in ids:
            emp_col.update_one({"_id": eid}, {"$set": {"status": "on_leave"}})
            con_col.update_many(
                {"employee_id": eid, "status": "active"},
                {"$set": {"status": "suspended"}},
            )
        return self._now_ms() - t0

    # ---- DELETE ----

    def _run_d1(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        for eid in self._pool_ids:
            col.delete_one({"_id": eid})
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d2(self) -> float:
        col = self._db.employees
        t0 = self._now_ms()
        col.delete_many({
            "status": "terminated",
            "email": {"$regex": "^pool_d2_"},
        })
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d3(self) -> float:
        emp_col = self._db.employees
        con_col = self._db.contracts
        t0 = self._now_ms()
        for eid in self._pool_ids:
            emp_col.delete_one({"_id": eid})
            con_col.delete_many({"employee_id": eid})
            self._db.leave_requests.delete_many({"employee_id": eid})
            self._db.evaluations.delete_many({"employee_id": eid})
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d4(self) -> float:
        """Delete by metadata condition."""
        col = self._db.employees
        t0 = self._now_ms()
        col.delete_many({
            "metadata.remote_eligible": True,
            "email": {"$regex": "^pool_d4_"},
        })
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d5(self) -> float:
        """Bulk delete by hire_date."""
        col = self._db.employees
        t0 = self._now_ms()
        col.delete_many({
            "hire_date": {"$lt": "2017-01-01"},
            "email": {"$regex": "^pool_d5_"},
        })
        self._pool_ids = []
        return self._now_ms() - t0

    def _run_d6(self) -> float:
        """Concurrent deletes from 4 threads."""
        chunk_size = len(self._pool_ids) // 4
        chunks = [self._pool_ids[i * chunk_size:(i + 1) * chunk_size] for i in range(4)]
        # Remaining items go to last chunk
        remainder = self._pool_ids[4 * chunk_size:]
        if remainder and chunks:
            chunks[-1] = chunks[-1] + remainder

        def _worker(id_chunk):
            client = self._new_client()
            db = client[CONNECTIONS["mongo"]["db"]]
            for eid in id_chunk:
                db.employees.delete_one({"_id": eid})
            client.close()

        t0 = self._now_ms()
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(_worker, c) for c in chunks]
            for f in as_completed(futures):
                f.result()
        self._pool_ids = []
        return self._now_ms() - t0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def contract_for_mongo(employee_id, idx: int) -> dict:
    """Wrap generate.contract_for with MongoDB employee_id."""
    c = contract_for(0, idx)
    c["employee_id"] = employee_id
    return c
