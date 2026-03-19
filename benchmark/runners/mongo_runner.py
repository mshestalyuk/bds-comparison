"""
MongoDB benchmark runner — implements all 12 scenarios.
"""
import random
from datetime import date, datetime

from pymongo import MongoClient, InsertOne, ASCENDING

from benchmark.config import CONNECTIONS, BATCH_SIZE
from benchmark.generate import (
    chunked, contract_for, employee_generator, evaluation_for, pool_employee,
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

        # Employees
        emp_col = self._db.employees
        all_ids = []
        gen = employee_generator(n)
        for batch in chunked(gen, BATCH_SIZE):
            result = emp_col.insert_many(batch)
            all_ids.extend(result.inserted_ids)

        # Indexes
        emp_col.create_index("email", unique=True)
        emp_col.create_index("department_id")
        emp_col.create_index("status")

        # Contracts
        con_col = self._db.contracts
        for batch_ids in chunked(enumerate(all_ids), BATCH_SIZE):
            docs = [contract_for_mongo(eid, i) for i, eid in batch_ids]
            con_col.insert_many(docs)
        con_col.create_index("employee_id")

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

        elif scenario_id in ("D1", "D2", "D3"):
            count  = 500 if scenario_id in ("D1", "D2") else 50
            tag    = scenario_id.lower()
            status = "terminated" if scenario_id == "D2" else "active"
            pool   = [pool_employee(tag, i, status=status) for i in range(count)]
            result = self._db.employees.insert_many(pool)
            self._pool_ids = result.inserted_ids
            if scenario_id == "D3":
                cons = [contract_for_mongo(eid, i) for i, eid in enumerate(self._pool_ids)]
                self._db.contracts.insert_many(cons)

    def after_scenario(self, scenario_id: str) -> None:
        if scenario_id in ("C1", "C2", "C3"):
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def contract_for_mongo(employee_id, idx: int) -> dict:
    """Wrap generate.contract_for with MongoDB employee_id (ObjectId or str)."""
    c = contract_for(0, idx)   # employee_id=0 placeholder
    c["employee_id"] = employee_id
    return c
