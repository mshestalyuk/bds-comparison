-- =============================================
-- Extra tables for MySQL (to reach 10 total)
-- Run after mysql-init.sql
-- =============================================

USE appdb;

-- 8. Salary change history
CREATE TABLE IF NOT EXISTS salary_history (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT NOT NULL,
    old_salary      DECIMAL(10, 2) NOT NULL,
    new_salary      DECIMAL(10, 2) NOT NULL,
    change_date     DATE NOT NULL DEFAULT (CURRENT_DATE),
    change_reason   VARCHAR(100),
    approved_by     INT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (approved_by) REFERENCES employees(id),
    INDEX idx_salary_hist_emp (employee_id, change_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Employee documents
CREATE TABLE IF NOT EXISTS employee_documents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    employee_id     INT NOT NULL,
    doc_type        ENUM('CV', 'certyfikat', 'dyplom', 'zaświadczenie', 'umowa', 'aneks',
                         'badania_lekarskie', 'szkolenie_BHP', 'inne') NOT NULL,
    title           VARCHAR(200) NOT NULL,
    file_path       VARCHAR(500),
    file_size_kb    INT,
    upload_date     DATE NOT NULL DEFAULT (CURRENT_DATE),
    expiry_date     DATE,
    metadata        JSON DEFAULT (JSON_OBJECT()),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    INDEX idx_docs_emp (employee_id),
    INDEX idx_docs_type (doc_type),
    INDEX idx_docs_expiry (expiry_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Audit log
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    table_name      VARCHAR(50) NOT NULL,
    record_id       INT,
    operation       ENUM('INSERT', 'UPDATE', 'DELETE', 'SELECT') NOT NULL,
    old_values      JSON,
    new_values      JSON,
    user_name       VARCHAR(100) DEFAULT (CURRENT_USER()),
    ip_address      VARCHAR(45),
    performed_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_table (table_name, performed_at),
    INDEX idx_audit_record (table_name, record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sample data
INSERT INTO salary_history (employee_id, old_salary, new_salary, change_date, change_reason, approved_by) VALUES
(1, 16000.00, 18500.00, '2024-01-01', 'Podwyżka roczna',        2),
(6, 12500.00, 14200.00, '2024-03-01', 'Awans na DevOps Engineer', 1),
(9, 14500.00, 16800.00, '2024-06-01', 'Przegląd wynagrodzeń',    1),
(7,  8500.00,  9800.00, '2024-01-01', 'Podwyżka roczna',        2),
(3, 15800.00, 17200.00, '2024-01-01', 'Podwyżka roczna',        2);

INSERT INTO employee_documents (employee_id, doc_type, title, file_path, file_size_kb, upload_date, expiry_date) VALUES
(1, 'certyfikat',        'Kubernetes CKA',                    '/docs/emp1/cka.pdf',          245, '2025-03-20', '2028-03-20'),
(1, 'badania_lekarskie', 'Badania okresowe 2025',             '/docs/emp1/badania_2025.pdf', 180, '2025-01-10', '2027-01-10'),
(6, 'certyfikat',        'AWS Solutions Architect Associate',  '/docs/emp6/aws_saa.pdf',      312, '2024-11-15', '2027-11-15'),
(9, 'dyplom',            'Mgr informatyka — Politechnika',    '/docs/emp9/dyplom_mgr.pdf',   520, '2019-06-30', NULL),
(2, 'szkolenie_BHP',     'BHP okresowe 2025',                 '/docs/emp2/bhp_2025.pdf',     95,  '2025-01-20', '2028-01-20');

INSERT INTO audit_log (table_name, record_id, operation, new_values, user_name) VALUES
('employees',  1, 'UPDATE', '{"salary_gross": 18500}',  'admin'),
('contracts',  6, 'UPDATE', '{"status": "active"}',     'admin'),
('employees', 10, 'INSERT', '{"email": "ewa.jankowska@firma.pl"}', 'admin');
