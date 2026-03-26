"""
Benchmark configuration — connection settings, dataset sizes, scenario definitions.

  - 24 scenarios (6 per CRUD operation)
  - Dataset sizes: 10K, 100K, 500K, 1M, 10M
  - Before/after index comparison mode
  - Normalization vs denormalization mode (hypothesis H3)
"""

DATASET_SIZES = [10_000, 100_000, 500_000, 1_000_000, 10_000_000]

ATTEMPTS = 3          # number of attempts per scenario (results are averaged)
BATCH_SIZE = 1_000    # records per INSERT batch during setup

# Per-runner max dataset (Redis is in-memory — cap at 100K to avoid OOM)
RUNNER_MAX_DATASET = {
    "postgres":       10_000_000,
    "mysql":          10_000_000,
    "mongo":          10_000_000,
    "redis":            100_000,
    "postgres_denorm": 10_000_000,
    "mysql_denorm":    10_000_000,
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
    # Denormalized schemas use the same connections but different DB/schema
    "postgres_denorm": {
        "host":     "localhost",
        "port":     5432,
        "dbname":   "appdb_denorm",
        "user":     "admin",
        "password": "postgres_secret_123",
    },
    "mysql_denorm": {
        "host":     "localhost",
        "port":     3306,
        "database": "appdb_denorm",
        "user":     "admin",
        "password": "mysql_secret_123",
    },
}

# ---------------------------------------------------------------------------
# 24 test scenarios — 6 per CRUD operation
# ---------------------------------------------------------------------------

SCENARIOS = [
    # --- CREATE (6) ---
    {"id": "C1", "name": "Single Insert",
     "operation": "CREATE",
     "desc": "Insert 100 employees one by one"},
    {"id": "C2", "name": "Batch Insert",
     "operation": "CREATE",
     "desc": "Insert 10,000 employees in batches of 1,000"},
    {"id": "C3", "name": "Transactional Insert",
     "operation": "CREATE",
     "desc": "Insert employee + contract + evaluation in one transaction (50×)"},
    {"id": "C4", "name": "Insert with JSON/semi-structured",
     "operation": "CREATE",
     "desc": "Insert 500 employees with JSON metadata field"},
    {"id": "C5", "name": "Concurrent Insert",
     "operation": "CREATE",
     "desc": "Insert 1,000 employees from 4 concurrent threads"},
    {"id": "C6", "name": "Upsert / ON CONFLICT",
     "operation": "CREATE",
     "desc": "Insert-or-update 500 employees (half exist, half new)"},

    # --- READ (6) ---
    {"id": "R1", "name": "Lookup by PK",
     "operation": "READ",
     "desc": "Fetch single employee by primary key (1,000 lookups)"},
    {"id": "R2", "name": "Filtered Search",
     "operation": "READ",
     "desc": "Filter employees by department + salary range (100 queries)"},
    {"id": "R3", "name": "Aggregation",
     "operation": "READ",
     "desc": "AVG salary and COUNT grouped by department (10 queries)"},
    {"id": "R4", "name": "JOIN / Lookup with related data",
     "operation": "READ",
     "desc": "Fetch employee + contract + latest evaluation (500 lookups)"},
    {"id": "R5", "name": "Full-text / Pattern Search",
     "operation": "READ",
     "desc": "Search employees by name pattern LIKE/regex (200 queries)"},
    {"id": "R6", "name": "Pagination / Range Scan",
     "operation": "READ",
     "desc": "Paginated listing with ORDER BY + LIMIT/OFFSET (100 pages)"},

    # --- UPDATE (6) ---
    {"id": "U1", "name": "Single Field Update",
     "operation": "UPDATE",
     "desc": "Update salary_gross of one random employee (1,000 updates)"},
    {"id": "U2", "name": "Bulk Update",
     "operation": "UPDATE",
     "desc": "Raise salary by 10% for all employees in each department (5 depts)"},
    {"id": "U3", "name": "Conditional Update",
     "operation": "UPDATE",
     "desc": "Set contract status=expired where end_date < today AND status=active"},
    {"id": "U4", "name": "Update JSON field",
     "operation": "UPDATE",
     "desc": "Update nested JSON metadata for 500 employees"},
    {"id": "U5", "name": "Concurrent Update",
     "operation": "UPDATE",
     "desc": "Update salary from 4 concurrent threads (1,000 total)"},
    {"id": "U6", "name": "Multi-table / Multi-key Update",
     "operation": "UPDATE",
     "desc": "Update employee status + related contract status in one transaction (200×)"},

    # --- DELETE (6) ---
    {"id": "D1", "name": "Delete by PK",
     "operation": "DELETE",
     "desc": "Delete single employee by primary key (500 deletes)"},
    {"id": "D2", "name": "Conditional Delete",
     "operation": "DELETE",
     "desc": "Delete all employees with status=terminated"},
    {"id": "D3", "name": "Cascade Delete",
     "operation": "DELETE",
     "desc": "Delete employee + all related records (contracts, leaves) for 50 employees"},
    {"id": "D4", "name": "Delete with JSON condition",
     "operation": "DELETE",
     "desc": "Delete employees where JSON metadata matches condition (100)"},
    {"id": "D5", "name": "Bulk Delete by range",
     "operation": "DELETE",
     "desc": "Delete employees hired before a certain date (batch)"},
    {"id": "D6", "name": "Concurrent Delete",
     "operation": "DELETE",
     "desc": "Delete 500 employees from 4 concurrent threads"},
]

# How many operations each scenario performs (for ops/sec calculation)
SCENARIO_OPS = {
    "C1": 100,
    "C2": 10_000,
    "C3": 50,
    "C4": 500,
    "C5": 1_000,
    "C6": 500,
    "R1": 1_000,
    "R2": 100,
    "R3": 10,
    "R4": 500,
    "R5": 200,
    "R6": 100,
    "U1": 1_000,
    "U2": 5,
    "U3": 1,
    "U4": 500,
    "U5": 1_000,
    "U6": 200,
    "D1": 500,
    "D2": 1,
    "D3": 50,
    "D4": 100,
    "D5": 1,
    "D6": 500,
}

DEPT_CODES  = ["IT", "HR", "FIN", "MKT", "LOG"]
DEPT_IDS    = [1, 2, 3, 4, 5]

# ---------------------------------------------------------------------------
# Index comparison mode
# ---------------------------------------------------------------------------

# When running with --no-index flag, these indexes are dropped before benchmark
# and recreated after. This lets you compare performance with/without indexes.
INDEXES_TO_TOGGLE = {
    "postgres": [
        "CREATE INDEX idx_employees_department ON employees(department_id)",
        "CREATE INDEX idx_employees_status ON employees(status)",
        "CREATE INDEX idx_employees_salary ON employees(salary_gross)",
        "CREATE INDEX idx_employees_name ON employees(last_name, first_name)",
        "CREATE INDEX idx_employees_hire_date ON employees(hire_date)",
        "CREATE INDEX idx_contracts_employee ON contracts(employee_id)",
        "CREATE INDEX idx_contracts_status ON contracts(status)",
        "CREATE INDEX idx_contracts_end_date ON contracts(end_date)",
        "CREATE INDEX idx_leave_employee_date ON leave_requests(employee_id, start_date DESC)",
        "CREATE INDEX idx_evaluations_employee ON evaluations(employee_id, period)",
    ],
    "mysql": [
        "CREATE INDEX idx_employees_salary ON employees(salary_gross)",
        "CREATE INDEX idx_employees_name ON employees(last_name, first_name)",
        "CREATE INDEX idx_employees_hire_date ON employees(hire_date)",
        "CREATE INDEX idx_contracts_status ON contracts(status)",
        "CREATE INDEX idx_contracts_end_date ON contracts(end_date)",
    ],
}
