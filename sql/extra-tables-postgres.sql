-- =============================================
-- Extra tables to reach 10 in relational schema
-- (requirement: at least 10 tables for 4.0)
--
-- Existing 7: departments, employees, contracts,
--             leave_requests, trainings,
--             training_participants, evaluations
--
-- New 3: salary_history, employee_documents, audit_log
-- =============================================

-- === PostgreSQL version ===
-- Run after postgres-init.sql

-- 8. Salary change history
CREATE TABLE IF NOT EXISTS salary_history (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    old_salary      NUMERIC(10, 2) NOT NULL,
    new_salary      NUMERIC(10, 2) NOT NULL,
    change_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    change_reason   VARCHAR(100),
    approved_by     INT REFERENCES employees(id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_salary_hist_emp ON salary_history(employee_id, change_date DESC);

-- 9. Employee documents (metadata only, no BLOBs)
CREATE TABLE IF NOT EXISTS employee_documents (
    id              SERIAL PRIMARY KEY,
    employee_id     INT NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    doc_type        VARCHAR(50) NOT NULL CHECK (doc_type IN (
        'CV', 'certyfikat', 'dyplom', 'zaświadczenie', 'umowa', 'aneks',
        'badania_lekarskie', 'szkolenie_BHP', 'inne'
    )),
    title           VARCHAR(200) NOT NULL,
    file_path       VARCHAR(500),
    file_size_kb    INT,
    upload_date     DATE NOT NULL DEFAULT CURRENT_DATE,
    expiry_date     DATE,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_docs_emp ON employee_documents(employee_id);
CREATE INDEX IF NOT EXISTS idx_docs_type ON employee_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_docs_expiry ON employee_documents(expiry_date);

-- 10. Audit log (tracks all CRUD operations for security analysis)
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    table_name      VARCHAR(50) NOT NULL,
    record_id       INT,
    operation       VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE', 'SELECT')),
    old_values      JSONB,
    new_values      JSONB,
    user_name       VARCHAR(100) DEFAULT CURRENT_USER,
    ip_address      VARCHAR(45),
    performed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log(table_name, performed_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_record ON audit_log(table_name, record_id);

-- Sample data for salary_history
INSERT INTO salary_history (employee_id, old_salary, new_salary, change_date, change_reason, approved_by) VALUES
(1, 16000.00, 18500.00, '2024-01-01', 'Podwyżka roczna',        2),
(6, 12500.00, 14200.00, '2024-03-01', 'Awans na DevOps Engineer', 1),
(9, 14500.00, 16800.00, '2024-06-01', 'Przegląd wynagrodzeń',    1),
(7,  8500.00,  9800.00, '2024-01-01', 'Podwyżka roczna',        2),
(3, 15800.00, 17200.00, '2024-01-01', 'Podwyżka roczna',        2);

-- Sample data for employee_documents
INSERT INTO employee_documents (employee_id, doc_type, title, file_path, file_size_kb, upload_date, expiry_date) VALUES
(1, 'certyfikat',        'Kubernetes CKA',                    '/docs/emp1/cka.pdf',          245, '2025-03-20', '2028-03-20'),
(1, 'badania_lekarskie', 'Badania okresowe 2025',             '/docs/emp1/badania_2025.pdf', 180, '2025-01-10', '2027-01-10'),
(6, 'certyfikat',        'AWS Solutions Architect Associate',  '/docs/emp6/aws_saa.pdf',      312, '2024-11-15', '2027-11-15'),
(9, 'dyplom',            'Mgr informatyka — Politechnika',    '/docs/emp9/dyplom_mgr.pdf',   520, '2019-06-30', NULL),
(2, 'szkolenie_BHP',     'BHP okresowe 2025',                 '/docs/emp2/bhp_2025.pdf',     95,  '2025-01-20', '2028-01-20'),
(3, 'certyfikat',        'ACCA Qualification',                '/docs/emp3/acca.pdf',          410, '2023-09-01', '2026-09-01'),
(7, 'zaświadczenie',     'RODO — przetwarzanie danych',       '/docs/emp7/rodo.pdf',          88,  '2025-04-10', '2026-04-10');

-- Sample audit_log entries
INSERT INTO audit_log (table_name, record_id, operation, new_values, user_name) VALUES
('employees',  1, 'UPDATE', '{"salary_gross": 18500}',  'admin'),
('contracts',  6, 'UPDATE', '{"status": "active"}',     'admin'),
('employees', 10, 'INSERT', '{"email": "ewa.jankowska@firma.pl"}', 'admin');
