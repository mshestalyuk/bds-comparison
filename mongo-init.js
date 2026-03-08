// =============================================
// System Ewidencji Personelu - MongoDB
// Collections: departments, employees, contracts,
//              leave_requests, trainings, evaluations
// =============================================

db = db.getSiblingDB('appdb');

// --- 1. Departments ---
db.departments.drop();
db.departments.insertMany([
    { _id: ObjectId("665a00000000000000000001"), code: "IT",  name: "Dział IT",               location: "Budynek A, piętro 3", manager_email: "jan.kowalski@firma.pl",      budget_yearly: 850000, created_at: new Date("2020-01-15") },
    { _id: ObjectId("665a00000000000000000002"), code: "HR",  name: "Dział Kadr i Płac",      location: "Budynek A, piętro 1", manager_email: "anna.nowak@firma.pl",        budget_yearly: 420000, created_at: new Date("2020-01-15") },
    { _id: ObjectId("665a00000000000000000003"), code: "FIN", name: "Dział Finansów",         location: "Budynek B, piętro 2", manager_email: "piotr.zielinski@firma.pl",   budget_yearly: 560000, created_at: new Date("2020-02-01") },
    { _id: ObjectId("665a00000000000000000004"), code: "MKT", name: "Dział Marketingu",       location: "Budynek C, piętro 1", manager_email: "maria.wisniewska@firma.pl",  budget_yearly: 720000, created_at: new Date("2020-03-10") },
    { _id: ObjectId("665a00000000000000000005"), code: "LOG", name: "Dział Logistyki",        location: "Budynek D, parter",   manager_email: "tomasz.lewandowski@firma.pl", budget_yearly: 380000, created_at: new Date("2020-04-01") }
]);

// --- 2. Employees ---
db.employees.drop();
db.employees.insertMany([
    { _id: ObjectId("665b00000000000000000001"), first_name: "Jan",        last_name: "Kowalski",    pesel: "85010112345", email: "jan.kowalski@firma.pl",         phone: "+48 501 111 001", date_of_birth: new Date("1985-01-01"), hire_date: new Date("2020-02-01"), position: "Kierownik Działu IT",          department_id: ObjectId("665a00000000000000000001"), salary_gross: 18500.00, status: "active",   address: { street: "ul. Marszałkowska 10/5", city: "Warszawa", zip: "00-001" } },
    { _id: ObjectId("665b00000000000000000002"), first_name: "Anna",       last_name: "Nowak",       pesel: "90051298765", email: "anna.nowak@firma.pl",           phone: "+48 501 111 002", date_of_birth: new Date("1990-05-12"), hire_date: new Date("2020-02-01"), position: "Kierownik Działu HR",          department_id: ObjectId("665a00000000000000000002"), salary_gross: 16000.00, status: "active",   address: { street: "ul. Nowy Świat 22/8",    city: "Warszawa", zip: "00-100" } },
    { _id: ObjectId("665b00000000000000000003"), first_name: "Piotr",      last_name: "Zieliński",   pesel: "88030356789", email: "piotr.zielinski@firma.pl",      phone: "+48 501 111 003", date_of_birth: new Date("1988-03-03"), hire_date: new Date("2020-03-15"), position: "Kierownik Działu Finansów",    department_id: ObjectId("665a00000000000000000003"), salary_gross: 17200.00, status: "active",   address: { street: "ul. Piękna 7/3",         city: "Warszawa", zip: "00-200" } },
    { _id: ObjectId("665b00000000000000000004"), first_name: "Maria",      last_name: "Wiśniewska",  pesel: "92071143210", email: "maria.wisniewska@firma.pl",     phone: "+48 501 111 004", date_of_birth: new Date("1992-07-11"), hire_date: new Date("2020-06-01"), position: "Kierownik Działu Marketingu",  department_id: ObjectId("665a00000000000000000004"), salary_gross: 15500.00, status: "active",   address: { street: "ul. Hoża 15/12",         city: "Warszawa", zip: "00-400" } },
    { _id: ObjectId("665b00000000000000000005"), first_name: "Tomasz",     last_name: "Lewandowski", pesel: "82122054321", email: "tomasz.lewandowski@firma.pl",   phone: "+48 501 111 005", date_of_birth: new Date("1982-12-20"), hire_date: new Date("2020-04-15"), position: "Kierownik Działu Logistyki",   department_id: ObjectId("665a00000000000000000005"), salary_gross: 14800.00, status: "active",   address: { street: "ul. Żelazna 30/1",       city: "Warszawa", zip: "00-800" } },
    { _id: ObjectId("665b00000000000000000006"), first_name: "Katarzyna",  last_name: "Wójcik",      pesel: "95030912345", email: "katarzyna.wojcik@firma.pl",     phone: "+48 501 111 006", date_of_birth: new Date("1995-03-09"), hire_date: new Date("2021-01-10"), position: "DevOps Engineer",              department_id: ObjectId("665a00000000000000000001"), salary_gross: 14200.00, status: "active",   address: { street: "ul. Mokotowska 5/9",     city: "Warszawa", zip: "00-640" } },
    { _id: ObjectId("665b00000000000000000007"), first_name: "Michał",     last_name: "Kamiński",    pesel: "91080267890", email: "michal.kaminski@firma.pl",      phone: "+48 501 111 007", date_of_birth: new Date("1991-08-02"), hire_date: new Date("2021-03-01"), position: "Specjalista ds. Rekrutacji",   department_id: ObjectId("665a00000000000000000002"), salary_gross:  9800.00, status: "active",   address: { street: "ul. Puławska 100/22",    city: "Warszawa", zip: "02-600" } },
    { _id: ObjectId("665b00000000000000000008"), first_name: "Aleksandra", last_name: "Dąbrowska",   pesel: "93042011111", email: "aleksandra.dabrowska@firma.pl", phone: "+48 501 111 008", date_of_birth: new Date("1993-04-20"), hire_date: new Date("2022-06-01"), position: "Analityk Finansowy",           department_id: ObjectId("665a00000000000000000003"), salary_gross: 11500.00, status: "on_leave", address: { street: "ul. Grójecka 45/7",      city: "Warszawa", zip: "02-030" } },
    { _id: ObjectId("665b00000000000000000009"), first_name: "Rafał",      last_name: "Szymański",   pesel: "87060533333", email: "rafal.szymanski@firma.pl",      phone: "+48 501 111 009", date_of_birth: new Date("1987-06-05"), hire_date: new Date("2019-09-01"), position: "Backend Developer",            department_id: ObjectId("665a00000000000000000001"), salary_gross: 16800.00, status: "active",   address: { street: "ul. Chmielna 20/3",      city: "Warszawa", zip: "00-020" } },
    { _id: ObjectId("665b0000000000000000000a"), first_name: "Ewa",        last_name: "Jankowska",   pesel: "96110244444", email: "ewa.jankowska@firma.pl",        phone: "+48 501 111 010", date_of_birth: new Date("1996-11-02"), hire_date: new Date("2023-01-15"), position: "Specjalista ds. Social Media", department_id: ObjectId("665a00000000000000000004"), salary_gross:  9200.00, status: "active",   address: { street: "ul. Koszykowa 8/16",     city: "Kraków",   zip: "30-001" } }
]);

// --- 3. Contracts ---
db.contracts.drop();
db.contracts.insertMany([
    { employee_id: ObjectId("665b00000000000000000001"), type: "umowa o pracę",  start_date: new Date("2020-02-01"), end_date: null,                      working_hours: 40, probation_end: new Date("2020-05-01"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000002"), type: "umowa o pracę",  start_date: new Date("2020-02-01"), end_date: null,                      working_hours: 40, probation_end: new Date("2020-05-01"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000003"), type: "umowa o pracę",  start_date: new Date("2020-03-15"), end_date: null,                      working_hours: 40, probation_end: new Date("2020-06-15"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000004"), type: "umowa o pracę",  start_date: new Date("2020-06-01"), end_date: null,                      working_hours: 40, probation_end: new Date("2020-09-01"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000005"), type: "umowa o pracę",  start_date: new Date("2020-04-15"), end_date: null,                      working_hours: 40, probation_end: new Date("2020-07-15"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000006"), type: "umowa o pracę",  start_date: new Date("2021-01-10"), end_date: new Date("2024-01-09"),    working_hours: 40, probation_end: new Date("2021-04-10"), status: "active" },
    { employee_id: ObjectId("665b00000000000000000007"), type: "umowa zlecenie", start_date: new Date("2021-03-01"), end_date: new Date("2025-03-01"),    working_hours: 30, probation_end: null,                   status: "active" },
    { employee_id: ObjectId("665b00000000000000000008"), type: "umowa o pracę",  start_date: new Date("2022-06-01"), end_date: new Date("2025-06-01"),    working_hours: 40, probation_end: new Date("2022-09-01"), status: "suspended" },
    { employee_id: ObjectId("665b00000000000000000009"), type: "umowa o pracę",  start_date: new Date("2019-09-01"), end_date: null,                      working_hours: 40, probation_end: new Date("2019-12-01"), status: "active" },
    { employee_id: ObjectId("665b0000000000000000000a"), type: "umowa o pracę",  start_date: new Date("2023-01-15"), end_date: new Date("2026-01-14"),    working_hours: 40, probation_end: new Date("2023-04-15"), status: "active" }
]);

// --- 4. Leave Requests ---
db.leave_requests.drop();
db.leave_requests.insertMany([
    { employee_id: ObjectId("665b00000000000000000001"), type: "wypoczynkowy",    start_date: new Date("2025-07-01"), end_date: new Date("2025-07-14"), days: 10,  status: "approved", approved_by: "anna.nowak@firma.pl",       created_at: new Date("2025-05-20") },
    { employee_id: ObjectId("665b00000000000000000006"), type: "wypoczynkowy",    start_date: new Date("2025-08-11"), end_date: new Date("2025-08-22"), days: 10,  status: "pending",  approved_by: null,                        created_at: new Date("2025-06-15") },
    { employee_id: ObjectId("665b00000000000000000008"), type: "macierzyński",    start_date: new Date("2025-03-01"), end_date: new Date("2025-09-01"), days: 130, status: "approved", approved_by: "anna.nowak@firma.pl",       created_at: new Date("2025-02-10") },
    { employee_id: ObjectId("665b00000000000000000009"), type: "wypoczynkowy",    start_date: new Date("2025-06-16"), end_date: new Date("2025-06-20"), days: 5,   status: "approved", approved_by: "jan.kowalski@firma.pl",     created_at: new Date("2025-05-30") },
    { employee_id: ObjectId("665b00000000000000000003"), type: "na żądanie",      start_date: new Date("2025-09-05"), end_date: new Date("2025-09-05"), days: 1,   status: "approved", approved_by: "anna.nowak@firma.pl",       created_at: new Date("2025-09-05") },
    { employee_id: ObjectId("665b0000000000000000000a"), type: "wypoczynkowy",    start_date: new Date("2025-12-23"), end_date: new Date("2025-12-31"), days: 5,   status: "pending",  approved_by: null,                        created_at: new Date("2025-10-01") },
    { employee_id: ObjectId("665b00000000000000000007"), type: "okolicznościowy", start_date: new Date("2025-05-10"), end_date: new Date("2025-05-11"), days: 2,   status: "approved", approved_by: "anna.nowak@firma.pl",       created_at: new Date("2025-04-28") }
]);

// --- 5. Trainings ---
db.trainings.drop();
db.trainings.insertMany([
    { title: "Kubernetes Advanced",             provider: "Cloud Academy",            date: new Date("2025-03-15"), duration_hours: 16, cost: 3500.00, participants: [ObjectId("665b00000000000000000001"), ObjectId("665b00000000000000000006"), ObjectId("665b00000000000000000009")], status: "completed" },
    { title: "Szkolenie BHP - okresowe",        provider: "BHP Consulting Sp. z o.o.",date: new Date("2025-01-20"), duration_hours: 8,  cost: 250.00,  participants: [ObjectId("665b00000000000000000001"), ObjectId("665b00000000000000000002"), ObjectId("665b00000000000000000003"), ObjectId("665b00000000000000000004"), ObjectId("665b00000000000000000005")], status: "completed" },
    { title: "RODO - ochrona danych osobowych", provider: "Kancelaria Prawna Lex",   date: new Date("2025-04-10"), duration_hours: 4,  cost: 800.00,  participants: [ObjectId("665b00000000000000000002"), ObjectId("665b00000000000000000007")], status: "completed" },
    { title: "AWS Solutions Architect",          provider: "AWS Training",            date: new Date("2025-10-05"), duration_hours: 40, cost: 6200.00, participants: [ObjectId("665b00000000000000000006"), ObjectId("665b00000000000000000009")], status: "scheduled" },
    { title: "Leadership & Management",         provider: "ICAN Institute",          date: new Date("2025-06-20"), duration_hours: 24, cost: 4500.00, participants: [ObjectId("665b00000000000000000001"), ObjectId("665b00000000000000000002"), ObjectId("665b00000000000000000003"), ObjectId("665b00000000000000000004"), ObjectId("665b00000000000000000005")], status: "completed" },
    { title: "Google Analytics 4",               provider: "Google Partners",         date: new Date("2025-11-12"), duration_hours: 8,  cost: 1200.00, participants: [ObjectId("665b00000000000000000004"), ObjectId("665b0000000000000000000a")], status: "scheduled" }
]);

// --- 6. Evaluations ---
db.evaluations.drop();
db.evaluations.insertMany([
    { employee_id: ObjectId("665b00000000000000000001"), evaluator_id: ObjectId("665b00000000000000000002"), period: "2024-H2", date: new Date("2025-01-15"), scores: { technical: 5, leadership: 5, communication: 4, teamwork: 5, initiative: 5 }, overall: 4.8, comments: "Doskonały lider zespołu. Wdrożył nową infrastrukturę CI/CD.",            recommendation: "awans" },
    { employee_id: ObjectId("665b00000000000000000006"), evaluator_id: ObjectId("665b00000000000000000001"), period: "2024-H2", date: new Date("2025-01-18"), scores: { technical: 5, leadership: 3, communication: 4, teamwork: 4, initiative: 5 }, overall: 4.2, comments: "Świetne umiejętności techniczne. Zautomatyzowała procesy deploymentu.",  recommendation: "podwyżka" },
    { employee_id: ObjectId("665b00000000000000000009"), evaluator_id: ObjectId("665b00000000000000000001"), period: "2024-H2", date: new Date("2025-01-18"), scores: { technical: 5, leadership: 3, communication: 3, teamwork: 4, initiative: 4 }, overall: 3.8, comments: "Solidny developer. Powinien popracować nad komunikacją.",               recommendation: "szkolenie" },
    { employee_id: ObjectId("665b00000000000000000007"), evaluator_id: ObjectId("665b00000000000000000002"), period: "2024-H2", date: new Date("2025-01-20"), scores: { technical: 3, leadership: 2, communication: 5, teamwork: 5, initiative: 4 }, overall: 3.8, comments: "Bardzo dobry kontakt z kandydatami. Wysoki wskaźnik zamknięć rekrutacji.", recommendation: "przedłużenie umowy" },
    { employee_id: ObjectId("665b0000000000000000000a"), evaluator_id: ObjectId("665b00000000000000000004"), period: "2024-H2", date: new Date("2025-01-22"), scores: { technical: 4, leadership: 2, communication: 5, teamwork: 4, initiative: 4 }, overall: 3.8, comments: "Kreatywna, świetne wyniki kampanii social media.",                       recommendation: "podwyżka" },
    { employee_id: ObjectId("665b00000000000000000005"), evaluator_id: ObjectId("665b00000000000000000002"), period: "2024-H2", date: new Date("2025-01-25"), scores: { technical: 4, leadership: 4, communication: 4, teamwork: 5, initiative: 3 }, overall: 4.0, comments: "Stabilne zarządzanie logistyką. Zredukował koszty transportu o 12%.",    recommendation: "premia" }
]);

// --- Indexes ---
db.employees.createIndex({ email: 1 }, { unique: true });
db.employees.createIndex({ department_id: 1 });
db.employees.createIndex({ status: 1 });
db.contracts.createIndex({ employee_id: 1 });
db.leave_requests.createIndex({ employee_id: 1, start_date: -1 });
db.evaluations.createIndex({ employee_id: 1, period: 1 });

print("=== MongoDB: System Ewidencji Personelu - dane załadowane ===");