# bds-comparison

**Database Management Systems Comparison** — CRUD benchmarking on a Polish HR dataset (System Ewidencji Personelu).

4 databases × 24 scenarios × 3 attempts × 5 dataset sizes.

| Database | Type | Data Model |
|---|---|---|
| PostgreSQL | Relational | Tables, SQL, JSONB |
| MySQL | Relational | Tables, SQL, JSON |
| MongoDB | Document | Collections, BSON |
| Redis | Key-Value | Hash, Set, Sorted Set |

---

## Requirements

```bash
# Python 3.10+
pip install psycopg2-binary mysql-connector-python pymongo redis

# Docker + Docker Compose
docker --version
docker compose version
```

---

## Quick Start

```bash
# 1. Start database containers
./db-manage.sh start

# 2. Load sample data (optional — benchmark loads its own)
./db-manage.sh load

# 3. Add extra tables
docker cp sql/extra-tables-postgres.sql postgresql:/tmp/
docker exec postgresql psql -U admin -d appdb -f /tmp/extra-tables-postgres.sql

docker cp sql/extra-tables-mysql.sql mysql:/tmp/
docker exec mysql bash -c "mysql -u admin -pmysql_secret_123 appdb < /tmp/extra-tables-mysql.sql"

# 4. (Optional) Create denormalized database for hypothesis H3
chmod +x setup-denorm.sh
./setup-denorm.sh

# 5. Install Python dependencies
pip install -r benchmark/requirements.txt

# 6. Run the benchmark
python3 -m benchmark.run_benchmark --db postgres,mysql,mongo,redis --size 10000
```

---

## Benchmark Commands

### Basic run (all databases, 10K records)

```bash
python3 -m benchmark.run_benchmark \
    --db postgres,mysql,mongo,redis \
    --size 10000
```

### Full benchmark (multiple sizes)

```bash
python3 -m benchmark.run_benchmark \
    --db postgres,mysql,mongo,redis \
    --size 10000,100000,500000,1000000
```

### Large datasets

```bash
python3 -m benchmark.run_benchmark \
    --db postgres,mysql,mongo \
    --size 500000,1000000,10000000
```

> Redis is capped at 100K records (in-memory). 10M-record runs for PG/MySQL/Mongo can take hours.

### Single database only

```bash
python3 -m benchmark.run_benchmark --db postgres --size 100000
```

### Specific scenarios only

```bash
python3 -m benchmark.run_benchmark \
    --db postgres \
    --scenarios C4,C5,C6,R4,R5,R6,U4,U5,U6,D4,D5,D6 \
    --size 10000,100000
```

### Index comparison — with vs without (hypothesis H1)

```bash
python3 -m benchmark.run_benchmark \
    --db postgres \
    --index-compare \
    --size 10000,100000,1000000
```

Runs the benchmark **twice**: once with indexes, once without. Results saved as `index_compare_*.csv`.

### Normalization vs denormalization (hypothesis H3)

```bash
python3 -m benchmark.run_benchmark \
    --db postgres \
    --denorm \
    --size 10000,100000,1000000
```

Benchmarks both the normalized schema (`postgres`) and denormalized flat table (`postgres_denorm`) side by side.

### EXPLAIN query plan analysis

```bash
# Via benchmark runner
python3 -m benchmark.run_benchmark --db postgres --explain --size 100000

# Standalone
python3 -m benchmark.explain_analyzer --db postgres
```

Outputs saved to `benchmark/results/explain_*.txt`.

---

## CLI Reference

```
python3 -m benchmark.run_benchmark [OPTIONS]

Options:
  --db TEXT            Comma-separated databases (default: postgres,mysql,mongo,redis)
  --size TEXT          Comma-separated dataset sizes (default: 10000,100000,500000,1000000,10000000)
  --attempts INT       Attempts per scenario (default: 3)
  --scenarios TEXT     Comma-separated scenario IDs (default: all 24)
  --denorm            Include denormalized schema runners
  --index-compare     Run with and without indexes
  --explain           Run EXPLAIN ANALYZE on representative queries
```

---

## Results

All output goes to `benchmark/results/`:

| File | Contents |
|---|---|
| `benchmark_<timestamp>.csv` | Full detail — every scenario, every attempt, every database |
| `summary_<timestamp>.csv` | Pivot table — scenario × database, avg_ms per cell |
| `index_compare_<timestamp>.csv` | Combined with/without index results |
| `explain_<db>_<timestamp>.txt` | EXPLAIN ANALYZE output for representative queries |

### Exploring results

```bash
# View latest results
ls -lt benchmark/results/ | head

# Quick look at summary
column -s, -t benchmark/results/summary_*.csv | head -30

# Filter by operation type
grep ",READ," benchmark/results/benchmark_*.csv

# Compare databases for a specific scenario
grep "R4" benchmark/results/summary_*.csv

# Sort by avg_ms to find slowest scenarios
sort -t, -k9 -n benchmark/results/benchmark_*.csv | tail -20
```

### Importing into a spreadsheet

The CSV files open directly in Excel, Google Sheets, or LibreOffice Calc. The summary file is already pivoted — databases as columns, scenarios as rows — ready for charting.

---

## 24 Test Scenarios

### CREATE (6)

| ID | Name | Operations | Description |
|---|---|---|---|
| C1 | Single Insert | 100 | Insert employees one by one |
| C2 | Batch Insert | 10,000 | Insert in batches of 1,000 |
| C3 | Transactional Insert | 50 | Employee + contract + evaluation in one transaction |
| C4 | Insert with JSON | 500 | Employees with semi-structured JSONB metadata |
| C5 | Concurrent Insert | 1,000 | Insert from 4 parallel threads |
| C6 | Upsert / ON CONFLICT | 500 | Insert-or-update (half exist, half new) |

### READ (6)

| ID | Name | Operations | Description |
|---|---|---|---|
| R1 | Lookup by PK | 1,000 | Fetch single employee by primary key |
| R2 | Filtered Search | 100 | Filter by department + salary range |
| R3 | Aggregation | 10 | AVG/COUNT/MIN/MAX grouped by department |
| R4 | JOIN / Lookup | 500 | Employee + contract + evaluation (3-table join) |
| R5 | Pattern Search | 200 | LIKE / regex on last_name |
| R6 | Pagination | 100 | ORDER BY + LIMIT/OFFSET, 50 per page |

### UPDATE (6)

| ID | Name | Operations | Description |
|---|---|---|---|
| U1 | Single Field Update | 1,000 | Update salary of random employees |
| U2 | Bulk Update | 5 | Raise salary 10% per department |
| U3 | Conditional Update | 1 | Expire contracts where end_date < today |
| U4 | Update JSON | 500 | Modify nested JSONB/JSON metadata field |
| U5 | Concurrent Update | 1,000 | Salary updates from 4 parallel threads |
| U6 | Multi-table Update | 200 | Employee status + contract status in one TX |

### DELETE (6)

| ID | Name | Operations | Description |
|---|---|---|---|
| D1 | Delete by PK | 500 | Delete single employee by ID |
| D2 | Conditional Delete | 1 | Delete all terminated employees |
| D3 | Cascade Delete | 50 | Delete employee + all related records |
| D4 | Delete by JSON | 100 | Delete where JSON metadata matches condition |
| D5 | Bulk Delete by Range | 1 | Delete employees hired before a date |
| D6 | Concurrent Delete | 500 | Delete from 4 parallel threads |

---

## Database Schema

### Normalized (10 tables)

```
departments ─────────┐
                     │
employees ←──────────┘  (FK department_id)
  ├── contracts          (FK employee_id, CASCADE)
  ├── leave_requests     (FK employee_id, CASCADE)
  ├── evaluations        (FK employee_id, CASCADE)
  ├── salary_history     (FK employee_id, CASCADE)
  └── employee_documents (FK employee_id, CASCADE)

trainings
  └── training_participants (FK training_id + employee_id)

audit_log (standalone)
```

### Denormalized (1 table)

```
employees_denorm
  — all employee fields
  — embedded: dept_code, dept_name, dept_budget
  — embedded: contract_type, contract_start, contract_end, contract_status
  — embedded: score_technical ... eval_overall
  — metadata (JSONB)
```

---

## Research Hypotheses

### H1: Indexes and Performance
> Adding indexes significantly improves SELECT performance at the cost of INSERT and UPDATE operations.

Test with `--index-compare`. Compare READ scenarios (R1-R6) and write scenarios (C1-C6, U1-U6) with and without indexes.

### H2: Dataset Size Impact
> Performance differences between database engines grow as record count increases.

Test by running with `--size 10000,100000,500000,1000000,10000000` and comparing the scaling curves.

### H3: Normalization vs Denormalization
> Denormalization improves read query performance at the cost of write operations.

Test with `--denorm`. Compare:
- **R4 (JOIN)**: normalized requires 3-table JOIN, denormalized is a single-row fetch
- **U2 (Bulk Update by dept)**: denormalized must update department info in every employee row

---

## Shell Access

```bash
./db-manage.sh psql     # PostgreSQL
./db-manage.sh mysql    # MySQL
./db-manage.sh mongo    # MongoDB
./db-manage.sh redis    # Redis
./db-manage.sh shell    # Interactive menu
```

### Useful queries to verify data

```sql
-- PostgreSQL / MySQL
SELECT COUNT(*) FROM employees;
SELECT * FROM v_employee_overview LIMIT 10;
SELECT department_id, COUNT(*), AVG(salary_gross) FROM employees GROUP BY department_id;
EXPLAIN ANALYZE SELECT * FROM employees WHERE department_id = 1 AND salary_gross > 10000;
```

```javascript
// MongoDB
db.employees.countDocuments()
db.employees.find().limit(5).pretty()
db.employees.aggregate([{$group: {_id: "$department_id", count: {$sum: 1}, avg: {$avg: "$salary_gross"}}}])
db.employees.find({department_id: 1, salary_gross: {$gt: 10000}}).explain("executionStats")
```

```
# Redis
DBSIZE
HGETALL employee:1000
SMEMBERS dept:IT:members
ZREVRANGE salary:ranking 0 4 WITHSCORES
```

---

## Project Structure

```
bds-comparison/
├── benchmark/
│   ├── config.py                 # 24 scenarios, dataset sizes, connections
│   ├── generate.py               # Data generators (normal + denormalized + JSON metadata)
│   ├── run_benchmark.py          # Main entry point
│   ├── explain_analyzer.py       # EXPLAIN ANALYZE tool
│   ├── requirements.txt          # Python dependencies
│   ├── results/                  # Output CSV and TXT files
│   └── runners/
│       ├── base_runner.py        # Abstract base class
│       ├── postgres_runner.py    # PostgreSQL (24 scenarios)
│       ├── mysql_runner.py       # MySQL (24 scenarios)
│       ├── mongo_runner.py       # MongoDB (24 scenarios)
│       ├── redis_runner.py       # Redis (24 scenarios)
│       └── postgres_denorm_runner.py  # Denormalized PostgreSQL (H3)
├── sql/
│   ├── extra-tables-postgres.sql # salary_history, employee_documents, audit_log
│   ├── extra-tables-mysql.sql    # Same for MySQL
│   └── postgres-denorm-init.sql  # Denormalized schema
├── docker-compose.yml            # All 4 database containers
├── db-manage.sh                  # Container lifecycle manager
├── setup-denorm.sh               # Create denormalized databases
├── postgres-init.sql             # PostgreSQL sample data
├── mysql-init.sql                # MySQL sample data
├── mongo-init.js                 # MongoDB sample data
└── redis-init.sh                 # Redis sample data
```

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `No module named 'mysql'` | `pip install mysql-connector-python` |
| `No module named 'pymongo'` | `pip install pymongo` |
| `No module named 'redis'` | `pip install redis` |
| `FATAL: database "appdb_denorm" does not exist` | Run `./setup-denorm.sh` |
| `deadlock detected` (U5) | Fixed in v2 — uses disjoint ID sets per thread |
| Redis OOM on large datasets | Redis is capped at 100K — this is by design |
| Benchmark takes too long | Use smaller sizes: `--size 10000,100000` |
| Container not running | `./db-manage.sh start` then `./db-manage.sh status` |