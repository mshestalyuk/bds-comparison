#!/usr/bin/env bash
# =============================================
# System Ewidencji Personelu - Redis
# Structures: hashes, sets, sorted sets, lists
# =============================================

REDIS_CLI="docker exec -i redis redis-cli -a redis_secret_123 --no-auth-warning"

echo ">>> Loading Redis sample data..."

# --- 1. Employee profiles (Hashes) ---
$REDIS_CLI HSET employee:1  first_name "Jan"        last_name "Kowalski"    email "jan.kowalski@firma.pl"        position "Kierownik Działu IT"          department "IT"  salary "18500" status "active"
$REDIS_CLI HSET employee:2  first_name "Anna"       last_name "Nowak"       email "anna.nowak@firma.pl"          position "Kierownik Działu HR"          department "HR"  salary "16000" status "active"
$REDIS_CLI HSET employee:3  first_name "Piotr"      last_name "Zieliński"   email "piotr.zielinski@firma.pl"     position "Kierownik Działu Finansów"    department "FIN" salary "17200" status "active"
$REDIS_CLI HSET employee:4  first_name "Maria"      last_name "Wiśniewska"  email "maria.wisniewska@firma.pl"    position "Kierownik Działu Marketingu"  department "MKT" salary "15500" status "active"
$REDIS_CLI HSET employee:5  first_name "Tomasz"     last_name "Lewandowski" email "tomasz.lewandowski@firma.pl"  position "Kierownik Działu Logistyki"   department "LOG" salary "14800" status "active"
$REDIS_CLI HSET employee:6  first_name "Katarzyna"  last_name "Wójcik"      email "katarzyna.wojcik@firma.pl"    position "DevOps Engineer"              department "IT"  salary "14200" status "active"
$REDIS_CLI HSET employee:7  first_name "Michał"     last_name "Kamiński"    email "michal.kaminski@firma.pl"     position "Specjalista ds. Rekrutacji"   department "HR"  salary "9800"  status "active"
$REDIS_CLI HSET employee:8  first_name "Aleksandra" last_name "Dąbrowska"   email "aleksandra.dabrowska@firma.pl" position "Analityk Finansowy"          department "FIN" salary "11500" status "on_leave"
$REDIS_CLI HSET employee:9  first_name "Rafał"      last_name "Szymański"   email "rafal.szymanski@firma.pl"     position "Backend Developer"            department "IT"  salary "16800" status "active"
$REDIS_CLI HSET employee:10 first_name "Ewa"        last_name "Jankowska"   email "ewa.jankowska@firma.pl"       position "Specjalista ds. Social Media" department "MKT" salary "9200"  status "active"

# --- 2. Department members (Sets) ---
$REDIS_CLI SADD dept:IT:members  1 6 9
$REDIS_CLI SADD dept:HR:members  2 7
$REDIS_CLI SADD dept:FIN:members 3 8
$REDIS_CLI SADD dept:MKT:members 4 10
$REDIS_CLI SADD dept:LOG:members 5

# --- 3. Salary ranking (Sorted Set) ---
$REDIS_CLI ZADD salary:ranking 18500 "employee:1"
$REDIS_CLI ZADD salary:ranking 17200 "employee:3"
$REDIS_CLI ZADD salary:ranking 16800 "employee:9"
$REDIS_CLI ZADD salary:ranking 16000 "employee:2"
$REDIS_CLI ZADD salary:ranking 15500 "employee:4"
$REDIS_CLI ZADD salary:ranking 14800 "employee:5"
$REDIS_CLI ZADD salary:ranking 14200 "employee:6"
$REDIS_CLI ZADD salary:ranking 11500 "employee:8"
$REDIS_CLI ZADD salary:ranking  9800 "employee:7"
$REDIS_CLI ZADD salary:ranking  9200 "employee:10"

# --- 4. Active sessions (Hashes + TTL) ---
$REDIS_CLI HSET session:jan.kowalski     login_at "2025-09-08T08:15:00Z" ip "10.0.1.101" user_agent "Chrome/128"
$REDIS_CLI HSET session:katarzyna.wojcik  login_at "2025-09-08T08:22:00Z" ip "10.0.1.115" user_agent "Firefox/130"
$REDIS_CLI HSET session:rafal.szymanski   login_at "2025-09-08T09:01:00Z" ip "10.0.1.120" user_agent "Chrome/128"
$REDIS_CLI EXPIRE session:jan.kowalski     28800
$REDIS_CLI EXPIRE session:katarzyna.wojcik 28800
$REDIS_CLI EXPIRE session:rafal.szymanski  28800

# --- 5. Pending leave requests queue (List) ---
$REDIS_CLI RPUSH leave:pending '{"employee_id":6,"type":"wypoczynkowy","start":"2025-08-11","end":"2025-08-22","days":10}'
$REDIS_CLI RPUSH leave:pending '{"employee_id":10,"type":"wypoczynkowy","start":"2025-12-23","end":"2025-12-31","days":5}'

# --- 6. Upcoming trainings (Sorted Set by date) ---
$REDIS_CLI ZADD trainings:upcoming 20251005 '{"id":4,"title":"AWS Solutions Architect","provider":"AWS Training","hours":40}'
$REDIS_CLI ZADD trainings:upcoming 20251112 '{"id":6,"title":"Google Analytics 4","provider":"Google Partners","hours":8}'

# --- 7. Department stats cache (Hashes + TTL) ---
$REDIS_CLI HSET stats:dept:IT  headcount 3 avg_salary "16500" budget "850000"
$REDIS_CLI HSET stats:dept:HR  headcount 2 avg_salary "12900" budget "420000"
$REDIS_CLI HSET stats:dept:FIN headcount 2 avg_salary "14350" budget "560000"
$REDIS_CLI HSET stats:dept:MKT headcount 2 avg_salary "12350" budget "720000"
$REDIS_CLI HSET stats:dept:LOG headcount 1 avg_salary "14800" budget "380000"
$REDIS_CLI EXPIRE stats:dept:IT  3600
$REDIS_CLI EXPIRE stats:dept:HR  3600
$REDIS_CLI EXPIRE stats:dept:FIN 3600
$REDIS_CLI EXPIRE stats:dept:MKT 3600
$REDIS_CLI EXPIRE stats:dept:LOG 3600

# --- 8. Email lookup index (Hash) ---
$REDIS_CLI HSET idx:email "jan.kowalski@firma.pl"         1
$REDIS_CLI HSET idx:email "anna.nowak@firma.pl"            2
$REDIS_CLI HSET idx:email "piotr.zielinski@firma.pl"       3
$REDIS_CLI HSET idx:email "maria.wisniewska@firma.pl"      4
$REDIS_CLI HSET idx:email "tomasz.lewandowski@firma.pl"    5
$REDIS_CLI HSET idx:email "katarzyna.wojcik@firma.pl"      6
$REDIS_CLI HSET idx:email "michal.kaminski@firma.pl"       7
$REDIS_CLI HSET idx:email "aleksandra.dabrowska@firma.pl"  8
$REDIS_CLI HSET idx:email "rafal.szymanski@firma.pl"       9
$REDIS_CLI HSET idx:email "ewa.jankowska@firma.pl"         10

echo "=== Redis: System Ewidencji Personelu - dane załadowane ==="