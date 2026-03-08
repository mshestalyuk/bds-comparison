-- =============================================
-- System Ewidencji Personelu - PostgreSQL
-- Tables: departments, employees, contracts,
--         leave_requests, trainings,
--         training_participants, evaluations
-- =============================================

-- === SCHEMA (idempotent) ===

DROP TABLE IF EXISTS evaluations CASCADE;
DROP TABLE IF EXISTS training_participants CASCADE;
DROP TABLE IF EXISTS trainings CASCADE;
DROP TABLE IF EXISTS leave_requests CASCADE;
DROP TABLE IF EXISTS contracts CASCADE;
DROP TABLE IF EXISTS employees CASCADE;
DROP TABLE IF EXISTS departments CASCADE;
DROP VIEW IF EXISTS v_employee_overview;

CREATE TABLE departments (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(10) UNIQUE NOT NULL,
    name            VARCHAR(100) NOT NULL,
    location        VARCHAR(150),
    manager_email   VARCHAR(100),
    budget_yearly   NUMERIC(12, 2) DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE employees (
    id              SERIAL PRIMARY KEY,
    first_name      VARCHAR(50) NOT NULL,
    last_name       VARCHAR(50) NOT NULL,
    pesel           VARCHAR(11) UNIQUE NOT NULL,
    email           VARCHAR(100) UNIQUE NOT NULL,
    phone           VARCHAR(20),
    date_of_birth   DATE NOT NULL,
    hire_date       DATE NOT NULL,
    position        VARCHAR(100) NOT NULL,
    department_id   INT REFERENCES departments(id) ON DELETE SET NULL,
    salary_gross    NUMERIC(10, 2) NOT NULL,
    status          VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'on_leave', 'terminated')),
    address_street  VARCHAR(150),
    address_city    VARCHAR(80),
    address_zip     VARCHAR(10),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE contracts (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    contract_type   VARCHAR(30) NOT NULL CHECK (contract_type IN ('umowa o pracę', 'umowa zlecenie', 'umowa o dzieło', 'B2B')),
    start_date      DATE NOT NULL,
    end_date        DATE,
    working_hours   INT DEFAULT 40,
    probation_end   DATE,
    status          VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'terminated', 'expired'))
);

CREATE TABLE leave_requests (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    leave_type      VARCHAR(30) NOT NULL CHECK (leave_type IN ('wypoczynkowy', 'na żądanie', 'macierzyński', 'ojcowski', 'okolicznościowy', 'bezpłatny', 'chorobowy')),
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    days            INT NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
    approved_by     INT REFERENCES employees(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE trainings (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(200) NOT NULL,
    provider        VARCHAR(150),
    training_date   DATE NOT NULL,
    duration_hours  INT NOT NULL,
    cost            NUMERIC(10, 2) DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'completed', 'cancelled'))
);

CREATE TABLE training_participants (
    id              SERIAL PRIMARY KEY,
    training_id     INT NOT NULL REFERENCES trainings(id) ON DELETE CASCADE,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    passed          BOOLEAN DEFAULT NULL,
    certificate_no  VARCHAR(50),
    UNIQUE(training_id, employee_id)
);

CREATE TABLE evaluations (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    evaluator_id    INT NOT NULL REFERENCES employees(id),
    period          VARCHAR(10) NOT NULL,
    eval_date       DATE NOT NULL,
    score_technical     SMALLINT CHECK (score_technical BETWEEN 1 AND 5),
    score_leadership    SMALLINT CHECK (score_leadership BETWEEN 1 AND 5),
    score_communication SMALLINT CHECK (score_communication BETWEEN 1 AND 5),
    score_teamwork      SMALLINT CHECK (score_teamwork BETWEEN 1 AND 5),
    score_initiative    SMALLINT CHECK (score_initiative BETWEEN 1 AND 5),
    overall         NUMERIC(2, 1),
    comments        TEXT,
    recommendation  VARCHAR(50),
    UNIQUE(employee_id, period)
);

CREATE INDEX idx_employees_department ON employees(department_id);
CREATE INDEX idx_employees_status ON employees(status);
CREATE INDEX idx_contracts_employee ON contracts(employee_id);
CREATE INDEX idx_leave_employee_date ON leave_requests(employee_id, start_date DESC);
CREATE INDEX idx_evaluations_employee ON evaluations(employee_id, period);

-- === DATA ===

INSERT INTO departments (code, name, location, manager_email, budget_yearly, created_at) VALUES
('IT',  'Dział IT',               'Budynek A, piętro 3', 'jan.kowalski@firma.pl',       850000, '2020-01-15'),
('HR',  'Dział Kadr i Płac',      'Budynek A, piętro 1', 'anna.nowak@firma.pl',         420000, '2020-01-15'),
('FIN', 'Dział Finansów',         'Budynek B, piętro 2', 'piotr.zielinski@firma.pl',    560000, '2020-02-01'),
('MKT', 'Dział Marketingu',       'Budynek C, piętro 1', 'maria.wisniewska@firma.pl',   720000, '2020-03-10'),
('LOG', 'Dział Logistyki',        'Budynek D, parter',   'tomasz.lewandowski@firma.pl',  380000, '2020-04-01');

INSERT INTO employees (first_name, last_name, pesel, email, phone, date_of_birth, hire_date, position, department_id, salary_gross, status, address_street, address_city, address_zip) VALUES
('Jan',        'Kowalski',     '85010112345', 'jan.kowalski@firma.pl',        '+48 501 111 001', '1985-01-01', '2020-02-01', 'Kierownik Działu IT',           1, 18500.00, 'active',   'ul. Marszałkowska 10/5',  'Warszawa', '00-001'),
('Anna',       'Nowak',        '90051298765', 'anna.nowak@firma.pl',          '+48 501 111 002', '1990-05-12', '2020-02-01', 'Kierownik Działu HR',           2, 16000.00, 'active',   'ul. Nowy Świat 22/8',     'Warszawa', '00-100'),
('Piotr',      'Zieliński',    '88030356789', 'piotr.zielinski@firma.pl',     '+48 501 111 003', '1988-03-03', '2020-03-15', 'Kierownik Działu Finansów',     3, 17200.00, 'active',   'ul. Piękna 7/3',          'Warszawa', '00-200'),
('Maria',      'Wiśniewska',   '92071143210', 'maria.wisniewska@firma.pl',    '+48 501 111 004', '1992-07-11', '2020-06-01', 'Kierownik Działu Marketingu',   4, 15500.00, 'active',   'ul. Hoża 15/12',          'Warszawa', '00-400'),
('Tomasz',     'Lewandowski',  '82122054321', 'tomasz.lewandowski@firma.pl',  '+48 501 111 005', '1982-12-20', '2020-04-15', 'Kierownik Działu Logistyki',    5, 14800.00, 'active',   'ul. Żelazna 30/1',        'Warszawa', '00-800'),
('Katarzyna',  'Wójcik',       '95030912345', 'katarzyna.wojcik@firma.pl',    '+48 501 111 006', '1995-03-09', '2021-01-10', 'DevOps Engineer',               1, 14200.00, 'active',   'ul. Mokotowska 5/9',      'Warszawa', '00-640'),
('Michał',     'Kamiński',     '91080267890', 'michal.kaminski@firma.pl',     '+48 501 111 007', '1991-08-02', '2021-03-01', 'Specjalista ds. Rekrutacji',     2,  9800.00, 'active',   'ul. Puławska 100/22',     'Warszawa', '02-600'),
('Aleksandra', 'Dąbrowska',    '93042011111', 'aleksandra.dabrowska@firma.pl','+48 501 111 008', '1993-04-20', '2022-06-01', 'Analityk Finansowy',            3, 11500.00, 'on_leave', 'ul. Grójecka 45/7',       'Warszawa', '02-030'),
('Rafał',      'Szymański',    '87060533333', 'rafal.szymanski@firma.pl',     '+48 501 111 009', '1987-06-05', '2019-09-01', 'Backend Developer',             1, 16800.00, 'active',   'ul. Chmielna 20/3',       'Warszawa', '00-020'),
('Ewa',        'Jankowska',    '96110244444', 'ewa.jankowska@firma.pl',       '+48 501 111 010', '1996-11-02', '2023-01-15', 'Specjalista ds. Social Media',  4,  9200.00, 'active',   'ul. Koszykowa 8/16',      'Kraków',   '30-001');

INSERT INTO contracts (employee_id, contract_type, start_date, end_date, working_hours, probation_end, status) VALUES
(1,  'umowa o pracę',  '2020-02-01', NULL,          40, '2020-05-01', 'active'),
(2,  'umowa o pracę',  '2020-02-01', NULL,          40, '2020-05-01', 'active'),
(3,  'umowa o pracę',  '2020-03-15', NULL,          40, '2020-06-15', 'active'),
(4,  'umowa o pracę',  '2020-06-01', NULL,          40, '2020-09-01', 'active'),
(5,  'umowa o pracę',  '2020-04-15', NULL,          40, '2020-07-15', 'active'),
(6,  'umowa o pracę',  '2021-01-10', '2024-01-09',  40, '2021-04-10', 'active'),
(7,  'umowa zlecenie', '2021-03-01', '2025-03-01',  30, NULL,         'active'),
(8,  'umowa o pracę',  '2022-06-01', '2025-06-01',  40, '2022-09-01', 'suspended'),
(9,  'umowa o pracę',  '2019-09-01', NULL,          40, '2019-12-01', 'active'),
(10, 'umowa o pracę',  '2023-01-15', '2026-01-14',  40, '2023-04-15', 'active');

INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days, status, approved_by, created_at) VALUES
(1,  'wypoczynkowy',    '2025-07-01', '2025-07-14', 10,  'approved', 2,    '2025-05-20'),
(6,  'wypoczynkowy',    '2025-08-11', '2025-08-22', 10,  'pending',  NULL, '2025-06-15'),
(8,  'macierzyński',    '2025-03-01', '2025-09-01', 130, 'approved', 2,    '2025-02-10'),
(9,  'wypoczynkowy',    '2025-06-16', '2025-06-20', 5,   'approved', 1,    '2025-05-30'),
(3,  'na żądanie',      '2025-09-05', '2025-09-05', 1,   'approved', 2,    '2025-09-05'),
(10, 'wypoczynkowy',    '2025-12-23', '2025-12-31', 5,   'pending',  NULL, '2025-10-01'),
(7,  'okolicznościowy', '2025-05-10', '2025-05-11', 2,   'approved', 2,    '2025-04-28');

INSERT INTO trainings (title, provider, training_date, duration_hours, cost, status) VALUES
('Kubernetes Advanced',             'Cloud Academy',            '2025-03-15', 16, 3500.00, 'completed'),
('Szkolenie BHP - okresowe',        'BHP Consulting Sp. z o.o.','2025-01-20', 8,  250.00,  'completed'),
('RODO - ochrona danych osobowych', 'Kancelaria Prawna Lex',   '2025-04-10', 4,  800.00,  'completed'),
('AWS Solutions Architect',          'AWS Training',            '2025-10-05', 40, 6200.00, 'scheduled'),
('Leadership & Management',         'ICAN Institute',          '2025-06-20', 24, 4500.00, 'completed'),
('Google Analytics 4',               'Google Partners',         '2025-11-12', 8,  1200.00, 'scheduled');

INSERT INTO training_participants (training_id, employee_id, passed, certificate_no) VALUES
(1, 1, TRUE,  'K8S-2025-001'), (1, 6, TRUE,  'K8S-2025-002'), (1, 9, TRUE,  'K8S-2025-003'),
(2, 1, TRUE,  'BHP-2025-001'), (2, 2, TRUE,  'BHP-2025-002'), (2, 3, TRUE,  'BHP-2025-003'), (2, 4, TRUE,  'BHP-2025-004'), (2, 5, TRUE,  'BHP-2025-005'),
(3, 2, TRUE,  'RODO-2025-001'), (3, 7, TRUE, 'RODO-2025-002'),
(4, 6, NULL,  NULL), (4, 9, NULL, NULL),
(5, 1, TRUE,  'LDR-2025-001'), (5, 2, TRUE,  'LDR-2025-002'), (5, 3, TRUE,  'LDR-2025-003'), (5, 4, TRUE,  'LDR-2025-004'), (5, 5, TRUE,  'LDR-2025-005'),
(6, 4, NULL,  NULL), (6, 10, NULL, NULL);

INSERT INTO evaluations (employee_id, evaluator_id, period, eval_date, score_technical, score_leadership, score_communication, score_teamwork, score_initiative, overall, comments, recommendation) VALUES
(1,  2, '2024-H2', '2025-01-15', 5, 5, 4, 5, 5, 4.8, 'Doskonały lider zespołu. Wdrożył nową infrastrukturę CI/CD.',            'awans'),
(6,  1, '2024-H2', '2025-01-18', 5, 3, 4, 4, 5, 4.2, 'Świetne umiejętności techniczne. Zautomatyzowała procesy deploymentu.',  'podwyżka'),
(9,  1, '2024-H2', '2025-01-18', 5, 3, 3, 4, 4, 3.8, 'Solidny developer. Powinien popracować nad komunikacją.',               'szkolenie'),
(7,  2, '2024-H2', '2025-01-20', 3, 2, 5, 5, 4, 3.8, 'Bardzo dobry kontakt z kandydatami. Wysoki wskaźnik zamknięć.',          'przedłużenie umowy'),
(10, 4, '2024-H2', '2025-01-22', 4, 2, 5, 4, 4, 3.8, 'Kreatywna, świetne wyniki kampanii social media.',                       'podwyżka'),
(5,  2, '2024-H2', '2025-01-25', 4, 4, 4, 5, 3, 4.0, 'Stabilne zarządzanie logistyką. Zredukował koszty transportu o 12%.',    'premia');

-- === VIEW ===

CREATE OR REPLACE VIEW v_employee_overview AS
SELECT
    e.id,
    e.first_name || ' ' || e.last_name AS full_name,
    e.position,
    d.name AS department,
    e.salary_gross,
    e.status,
    c.contract_type,
    c.start_date AS contract_start,
    c.end_date AS contract_end
FROM employees e
LEFT JOIN departments d ON e.department_id = d.id
LEFT JOIN contracts c ON c.employee_id = e.id AND c.status IN ('active', 'suspended');