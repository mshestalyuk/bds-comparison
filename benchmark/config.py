"""
Benchmark configuration — connection settings, dataset sizes, scenario definitions.
"""

DATASET_SIZES = [10_000, 100_000, 1_000_000]

ATTEMPTS = 3          # number of attempts per scenario (results are averaged)
BATCH_SIZE = 1_000    # records per INSERT batch during setup

# Per-runner max dataset (Redis is in-memory — cap at 100K to avoid OOM)
RUNNER_MAX_DATASET = {
    "postgres": 1_000_000,
    "mysql":    1_000_000,
    "mongo":    1_000_000,
    "redis":    100_000,
}

CONNECTIONS = {
    "postgres": {
        "host":     "localhost",
        "port":     5432,
        "dbname":   "appdb",
        "user":     "admin",
        "password": "postgres_secret_123",
    },
    "mysql": {
        "host":     "localhost",
        "port":     3306,
        "database": "appdb",
        "user":     "admin",
        "password": "mysql_secret_123",
    },
    "mongo": {
        "host":     "localhost",
        "port":     27017,
        "db":       "appdb",
        "user":     "admin",
        "password": "mongo_secret_123",
    },
    "redis": {
        "host":     "localhost",
        "port":     6380,
        "password": "redis_secret_123",
    },
}

# 12 test scenarios — at least 3 per CRUD operation
SCENARIOS = [
    # --- CREATE ---
    {"id": "C1", "name": "Single Insert",         "operation": "CREATE",
     "desc": "Insert 100 employees one by one"},
    {"id": "C2", "name": "Batch Insert",          "operation": "CREATE",
     "desc": "Insert 10,000 employees in batches of 1,000"},
    {"id": "C3", "name": "Transactional Insert",  "operation": "CREATE",
     "desc": "Insert employee + contract + evaluation in one transaction (50×)"},

    # --- READ ---
    {"id": "R1", "name": "Lookup by PK",          "operation": "READ",
     "desc": "Fetch single employee by primary key (1,000 lookups)"},
    {"id": "R2", "name": "Filtered Search",       "operation": "READ",
     "desc": "Filter employees by department + salary range (100 queries)"},
    {"id": "R3", "name": "Aggregation",           "operation": "READ",
     "desc": "AVG salary and COUNT grouped by department (10 queries)"},

    # --- UPDATE ---
    {"id": "U1", "name": "Single Field Update",   "operation": "UPDATE",
     "desc": "Update salary_gross of one random employee (1,000 updates)"},
    {"id": "U2", "name": "Bulk Update",           "operation": "UPDATE",
     "desc": "Raise salary by 10% for all employees in each department (5 depts)"},
    {"id": "U3", "name": "Conditional Update",    "operation": "UPDATE",
     "desc": "Set contract status=expired where end_date < today AND status=active"},

    # --- DELETE ---
    {"id": "D1", "name": "Delete by PK",          "operation": "DELETE",
     "desc": "Delete single employee by primary key (500 deletes)"},
    {"id": "D2", "name": "Conditional Delete",    "operation": "DELETE",
     "desc": "Delete all employees with status=terminated"},
    {"id": "D3", "name": "Cascade Delete",        "operation": "DELETE",
     "desc": "Delete employee + all related records (contracts, leaves) for 50 employees"},
]

# How many operations each scenario performs (for ops/sec calculation)
SCENARIO_OPS = {
    "C1": 100,
    "C2": 10_000,
    "C3": 50,
    "R1": 1_000,
    "R2": 100,
    "R3": 10,
    "U1": 1_000,
    "U2": 5,       # 5 department bulk updates
    "U3": 1,       # 1 conditional update (N rows affected varies)
    "D1": 500,
    "D2": 1,       # 1 conditional delete (N rows affected varies)
    "D3": 50,
}

DEPT_CODES  = ["IT", "HR", "FIN", "MKT", "LOG"]
DEPT_IDS    = [1, 2, 3, 4, 5]
