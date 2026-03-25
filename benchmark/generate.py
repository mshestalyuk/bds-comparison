"""
Fast data generator for benchmark.
Uses pre-built name/city lists instead of calling Faker on every record
so that 1M+ records can be generated quickly.

Expanded: JSON metadata, pool generators for C4-C6, D4-D6, U4-U6.
"""
import json
import random
from datetime import date, timedelta
from itertools import islice
from typing import Iterator

# ---------------------------------------------------------------------------
# Static data pools (Polish locale)
# ---------------------------------------------------------------------------
FIRST_NAMES = [
    "Adam", "Aleksandra", "Anna", "Bartosz", "Dominika", "Ewa", "Filip",
    "Grzegorz", "Iwona", "Jan", "Joanna", "Kamil", "Katarzyna", "Krzysztof",
    "Łukasz", "Marek", "Maria", "Michał", "Monika", "Natalia", "Piotr",
    "Rafał", "Robert", "Sylwia", "Tomasz", "Weronika", "Zbigniew", "Zofia",
]
LAST_NAMES = [
    "Adamczyk", "Bąk", "Dąbrowski", "Jabłoński", "Jankowski", "Kamiński",
    "Kowalski", "Kowalczyk", "Kwiatkowski", "Lewandowski", "Malinowski",
    "Nowak", "Nowakowski", "Piotrowska", "Sikorski", "Szymański",
    "Wiśniewski", "Wójcik", "Woźniak", "Zieliński",
]
POSITIONS = [
    "Programista", "Analityk", "Specjalista", "Inżynier", "Administrator",
    "Konsultant", "Koordynator", "Kierownik", "Doradca", "Kontroler",
    "Referent", "Asystent", "Ekspert", "Starszy Programista", "Tester",
]
CITIES = [
    "Warszawa", "Kraków", "Łódź", "Wrocław", "Poznań", "Gdańsk",
    "Szczecin", "Bydgoszcz", "Lublin", "Katowice", "Białystok", "Gdynia",
]
STREETS = [
    "ul. Lipowa", "ul. Leśna", "ul. Słoneczna", "ul. Krótka",
    "ul. Długa", "ul. Polna", "ul. Kwiatowa", "ul. Nowa", "ul. Zielona",
    "al. Niepodległości", "ul. Mickiewicza", "ul. Kościuszki",
]
CONTRACT_TYPES = ["umowa o pracę", "umowa zlecenie", "umowa o dzieło", "B2B"]
LEAVE_TYPES = [
    "wypoczynkowy", "na żądanie", "okolicznościowy", "bezpłatny", "chorobowy",
]
STATUSES    = ["active"] * 80 + ["on_leave"] * 10 + ["terminated"] * 10
CONTRACT_ST = ["active"] * 85 + ["suspended"] * 10 + ["expired"] * 5
RECOMMENDATIONS = ["awans", "podwyżka", "szkolenie", "premia", "przedłużenie umowy"]

# Semi-structured metadata pools
SKILLS = [
    "Python", "Java", "Go", "Rust", "JavaScript", "TypeScript", "SQL",
    "Kubernetes", "Docker", "AWS", "Azure", "GCP", "Terraform", "Ansible",
    "React", "Angular", "Vue.js", "Node.js", "PostgreSQL", "MongoDB",
]
CERTIFICATIONS = [
    "AWS Solutions Architect", "CKA", "CKAD", "PMP", "PRINCE2",
    "ITIL v4", "CISSP", "CCNA", "Azure Administrator", "GCP Professional",
    "Scrum Master", "ISTQB", "ISO 27001 Lead Auditor",
]
LANGUAGES = ["polski", "angielski", "niemiecki", "francuski", "rosyjski", "ukraiński"]
LANGUAGE_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

_START_DATE = date(2015, 1, 1)
_END_DATE   = date(2024, 12, 31)
_DATE_RANGE = (_END_DATE - _START_DATE).days

_CONTRACT_START = date(2015, 1, 1)
_CONTRACT_RANGE = (_END_DATE - _CONTRACT_START).days


def _rand_date(start: date, days: int) -> date:
    return start + timedelta(days=random.randint(0, days))


def _generate_metadata() -> dict:
    """Generate semi-structured JSON metadata for an employee."""
    n_skills = random.randint(2, 6)
    n_certs  = random.randint(0, 3)
    n_langs  = random.randint(1, 3)
    return {
        "skills": random.sample(SKILLS, n_skills),
        "certifications": [
            {"name": c, "year": random.randint(2018, 2024)}
            for c in random.sample(CERTIFICATIONS, n_certs)
        ],
        "languages": [
            {"lang": l, "level": random.choice(LANGUAGE_LEVELS)}
            for l in random.sample(LANGUAGES, n_langs)
        ],
        "notes": f"Benchmark metadata record #{random.randint(1, 999999)}",
        "remote_eligible": random.choice([True, False]),
        "equipment": {
            "laptop": random.choice(["MacBook Pro", "ThinkPad X1", "Dell XPS", "HP EliteBook"]),
            "monitor_count": random.randint(1, 3),
        },
    }


# ---------------------------------------------------------------------------
# Public generator
# ---------------------------------------------------------------------------

def employee_generator(n: int, offset: int = 0, with_metadata: bool = False) -> Iterator[dict]:
    """
    Yield n employee dicts.  offset makes PESELs/emails globally unique
    when loading into multiple databases.
    """
    rc = random.choice
    rr = random.uniform

    for i in range(n):
        idx = offset + i
        pesel     = f"{idx + 1_000:011d}"
        email     = f"main_{idx}@bench.test"
        dept_id   = random.randint(1, 5)
        hire      = _rand_date(_START_DATE, _DATE_RANGE)
        dob       = hire - timedelta(days=random.randint(22 * 365, 55 * 365))
        salary    = round(rr(3_500, 25_000), 2)
        status    = rc(STATUSES)
        emp = {
            "first_name":     rc(FIRST_NAMES),
            "last_name":      rc(LAST_NAMES),
            "pesel":          pesel,
            "email":          email,
            "phone":          f"+48 6{idx % 100:02d} {(idx // 100) % 1000:03d} {(idx // 100_000) % 1000:03d}",
            "date_of_birth":  dob.isoformat(),
            "hire_date":      hire.isoformat(),
            "position":       rc(POSITIONS),
            "department_id":  dept_id,
            "salary_gross":   salary,
            "status":         status,
            "address_street": f"{rc(STREETS)} {random.randint(1, 200)}/{random.randint(1, 50)}",
            "address_city":   rc(CITIES),
            "address_zip":    f"{random.randint(0, 99):02d}-{random.randint(0, 999):03d}",
        }
        if with_metadata:
            emp["metadata"] = _generate_metadata()
        yield emp


def contract_for(employee_id: int, idx: int) -> dict:
    """Return a contract dict for the given employee_id."""
    start = _rand_date(_CONTRACT_START, _CONTRACT_RANGE)
    has_end = random.random() < 0.4
    end = (start + timedelta(days=random.randint(180, 1460))).isoformat() if has_end else None
    return {
        "employee_id":   employee_id,
        "contract_type": random.choice(CONTRACT_TYPES),
        "start_date":    start.isoformat(),
        "end_date":      end,
        "working_hours": random.choice([40, 30, 20]),
        "probation_end": (start + timedelta(days=90)).isoformat(),
        "status":        random.choice(CONTRACT_ST),
    }


def evaluation_for(employee_id: int, evaluator_id: int, period: str) -> dict:
    scores = [random.randint(1, 5) for _ in range(5)]
    return {
        "employee_id":           employee_id,
        "evaluator_id":          evaluator_id,
        "period":                period,
        "eval_date":             date(2025, 1, random.randint(1, 28)).isoformat(),
        "score_technical":       scores[0],
        "score_leadership":      scores[1],
        "score_communication":   scores[2],
        "score_teamwork":        scores[3],
        "score_initiative":      scores[4],
        "overall":               round(sum(scores) / 5, 1),
        "comments":              "Benchmark evaluation record.",
        "recommendation":        random.choice(RECOMMENDATIONS),
    }


def pool_employee(tag: str, i: int, status: str = "active",
                  with_metadata: bool = False) -> dict:
    """
    Generate a pool employee for CREATE/DELETE scenarios.
    tag examples: 'c1', 'c2', 'c3', 'd1', 'd2', 'd3', 'c4', 'c5', etc.
    """
    emp = {
        "first_name":     random.choice(FIRST_NAMES),
        "last_name":      random.choice(LAST_NAMES),
        "pesel":          f"{tag.upper()}{i:08d}"[:11],
        "email":          f"pool_{tag}_{i}@bench.test",
        "phone":          f"+48 700 {i % 1000:03d} {i // 1000 % 1000:03d}",
        "date_of_birth":  "1990-01-01",
        "hire_date":      "2020-01-01",
        "position":       "Tester Benchmark",
        "department_id":  random.randint(1, 5),
        "salary_gross":   round(random.uniform(4_000, 12_000), 2),
        "status":         status,
        "address_street": "ul. Testowa 1/1",
        "address_city":   "Warszawa",
        "address_zip":    "00-001",
    }
    if with_metadata:
        emp["metadata"] = _generate_metadata()
    return emp


# ---------------------------------------------------------------------------
# Denormalized employee generator (for H3 hypothesis)
# ---------------------------------------------------------------------------

def denorm_employee_generator(n: int, offset: int = 0) -> Iterator[dict]:
    """
    Yield n denormalized employee dicts — single flat record with embedded
    department info, contract, and latest evaluation scores.
    Used for the denormalized schema to test hypothesis H3.
    """
    dept_data = {
        1: {"dept_code": "IT",  "dept_name": "Dział IT",          "dept_budget": 850000},
        2: {"dept_code": "HR",  "dept_name": "Dział Kadr i Płac", "dept_budget": 420000},
        3: {"dept_code": "FIN", "dept_name": "Dział Finansów",    "dept_budget": 560000},
        4: {"dept_code": "MKT", "dept_name": "Dział Marketingu",  "dept_budget": 720000},
        5: {"dept_code": "LOG", "dept_name": "Dział Logistyki",   "dept_budget": 380000},
    }
    rc = random.choice
    rr = random.uniform

    for i in range(n):
        idx    = offset + i
        dept_id = random.randint(1, 5)
        dd     = dept_data[dept_id]
        hire   = _rand_date(_START_DATE, _DATE_RANGE)
        dob    = hire - timedelta(days=random.randint(22 * 365, 55 * 365))
        salary = round(rr(3_500, 25_000), 2)

        con_start = _rand_date(_CONTRACT_START, _CONTRACT_RANGE)
        has_end   = random.random() < 0.4
        con_end   = (con_start + timedelta(days=random.randint(180, 1460))).isoformat() if has_end else None

        scores = [random.randint(1, 5) for _ in range(5)]

        yield {
            # employee
            "first_name":     rc(FIRST_NAMES),
            "last_name":      rc(LAST_NAMES),
            "pesel":          f"{idx + 1_000:011d}",
            "email":          f"denorm_{idx}@bench.test",
            "phone":          f"+48 6{idx % 100:02d} {(idx // 100) % 1000:03d} {(idx // 100_000) % 1000:03d}",
            "date_of_birth":  dob.isoformat(),
            "hire_date":      hire.isoformat(),
            "position":       rc(POSITIONS),
            "salary_gross":   salary,
            "status":         rc(STATUSES),
            "address_street": f"{rc(STREETS)} {random.randint(1, 200)}/{random.randint(1, 50)}",
            "address_city":   rc(CITIES),
            "address_zip":    f"{random.randint(0, 99):02d}-{random.randint(0, 999):03d}",
            # embedded department
            "dept_code":      dd["dept_code"],
            "dept_name":      dd["dept_name"],
            "dept_budget":    dd["dept_budget"],
            # embedded contract
            "contract_type":  rc(CONTRACT_TYPES),
            "contract_start": con_start.isoformat(),
            "contract_end":   con_end,
            "contract_status": rc(CONTRACT_ST),
            "working_hours":  random.choice([40, 30, 20]),
            # embedded evaluation scores
            "score_technical":     scores[0],
            "score_leadership":    scores[1],
            "score_communication": scores[2],
            "score_teamwork":      scores[3],
            "score_initiative":    scores[4],
            "eval_overall":        round(sum(scores) / 5, 1),
            # JSON metadata
            "metadata":       json.dumps(_generate_metadata(), ensure_ascii=False),
        }


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def chunked(iterable, size: int):
    """Yield successive lists of `size` items from an iterable."""
    it = iter(iterable)
    while True:
        chunk = list(islice(it, size))
        if not chunk:
            break
        yield chunk
