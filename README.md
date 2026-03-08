# bds-comparison

Porównanie 4 baz danych na przykładzie **Systemu Ewidencji Personelu** — ten sam zestaw danych załadowany do MongoDB, PostgreSQL, MySQL i Redis.

## Struktura repo

```
.
├── README.md
├── db-manage.sh          # główny skrypt zarządzania stackiem
├── docker-compose.yml    # MongoDB 7.0.14, PostgreSQL 16.4, MySQL 8.4.2, Redis 7.2.6
├── mongo-init.js         # dane dla MongoDB (6 kolekcji)
├── postgres-init.sql     # dane dla PostgreSQL (7 tabel + widok)
├── mysql-init.sql        # dane dla MySQL (7 tabel + widok)
└── redis-init.sh         # dane dla Redis (8 struktur danych)
```

## Szybki start

```bash
# 1. Uruchom stack
./db-manage.sh start

# 2. Załaduj dane testowe
./db-manage.sh load

# 3. Wejdź do shella wybranej bazy
./db-manage.sh shell      # interaktywne menu
./db-manage.sh psql       # PostgreSQL
./db-manage.sh mongo      # MongoDB
./db-manage.sh mysql      # MySQL
./db-manage.sh redis      # Redis-CLI
```

## Komendy db-manage.sh

| Komenda     | Opis                                           |
|-------------|-------------------------------------------------|
| `start`     | Uruchom kontenery                               |
| `stop`      | Zatrzymaj kontenery                             |
| `restart`   | Restart kontenerów                              |
| `status`    | Status kontenerów                               |
| `logs`      | Podgląd logów (tail -f)                         |
| `load`      | Załaduj dane testowe do wszystkich baz          |
| `shell`     | Interaktywne menu wyboru shella bazy            |
| `mongo`     | Wejdź do mongosh                                |
| `psql`      | Wejdź do psql                                   |
| `mysql`     | Wejdź do mysql                                  |
| `redis`     | Wejdź do redis-cli                              |
| `destroy`   | Zatrzymaj kontenery + usuń wolumeny (DANE!)     |

## Model danych

**System Ewidencji Personelu** — 5 działów, 10 pracowników.

### Tabele (SQL) / Kolekcje (Mongo)

| #  | Nazwa                    | Opis                                        |
|----|--------------------------|---------------------------------------------|
| 1  | `departments`            | Działy firmy (IT, HR, FIN, MKT, LOG)        |
| 2  | `employees`              | Pracownicy z danymi osobowymi i adresami    |
| 3  | `contracts`              | Umowy (o pracę, zlecenie, B2B)              |
| 4  | `leave_requests`         | Wnioski urlopowe                            |
| 5  | `trainings`              | Szkolenia (BHP, K8s, AWS, RODO...)          |
| 6  | `training_participants`  | Uczestnicy szkoleń + certyfikaty            |
| 7  | `evaluations`            | Oceny pracownicze (5 kryteriów)             |

### Redis — struktury danych

| Klucz                  | Typ         | Opis                           |
|------------------------|-------------|--------------------------------|
| `employee:{id}`        | Hash        | Profil pracownika              |
| `dept:{code}:members`  | Set         | ID pracowników w dziale        |
| `salary:ranking`       | Sorted Set  | Ranking wynagrodzeń            |
| `session:{email}`      | Hash + TTL  | Aktywne sesje (8h TTL)         |
| `leave:pending`        | List        | Kolejka wniosków urlopowych    |
| `trainings:upcoming`   | Sorted Set  | Nadchodzące szkolenia          |
| `stats:dept:{code}`    | Hash + TTL  | Cache statystyk działów (1h)   |
| `idx:email`            | Hash        | Reverse index email → ID       |

## Przykładowe zapytania

```sql
-- PostgreSQL / MySQL: przegląd pracowników
SELECT * FROM v_employee_overview;

-- Top 3 najlepiej zarabiający
SELECT first_name, last_name, salary_gross
FROM employees ORDER BY salary_gross DESC LIMIT 3;
```

```javascript
// MongoDB: pracownicy działu IT
db.employees.find({ department_id: ObjectId("665a00000000000000000001") }).pretty()
```

```bash
# Redis: ranking wynagrodzeń (top 3)
ZREVRANGE salary:ranking 0 2 WITHSCORES
```

## Porty

| Baza       | Port  |
|------------|-------|
| MongoDB    | 27017 |
| PostgreSQL | 5432  |
| MySQL      | 3306  |
| Redis      | 6379  |

## Credentials

| Baza       | User    | Password              |
|------------|---------|------------------------|
| MongoDB    | admin   | mongo_secret_123       |
| PostgreSQL | admin   | postgres_secret_123    |
| MySQL      | admin   | mysql_secret_123       |
| Redis      | —       | redis_secret_123       |

> ⚠️ Zmień hasła przed użyciem w środowisku innym niż lokalne!