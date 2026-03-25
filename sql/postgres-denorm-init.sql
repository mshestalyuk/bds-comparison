-- =============================================
-- System Ewidencji Personelu - PostgreSQL (DENORMALIZED)
-- Single table: employees_denorm
-- For hypothesis H3: normalization vs denormalization
-- =============================================

DROP TABLE IF EXISTS employees_denorm CASCADE;

CREATE TABLE employees_denorm (
    id                  SERIAL PRIMARY KEY,
    -- employee fields
    first_name          VARCHAR(50) NOT NULL,
    last_name           VARCHAR(50) NOT NULL,
    pesel               VARCHAR(11) UNIQUE NOT NULL,
    email               VARCHAR(100) UNIQUE NOT NULL,
    phone               VARCHAR(20),
    date_of_birth       DATE NOT NULL,
    hire_date           DATE NOT NULL,
    position            VARCHAR(100) NOT NULL,
    salary_gross        NUMERIC(10, 2) NOT NULL,
    status              VARCHAR(20) DEFAULT 'active',
    address_street      VARCHAR(150),
    address_city        VARCHAR(80),
    address_zip         VARCHAR(10),
    -- embedded department (denormalized)
    dept_code           VARCHAR(10) NOT NULL,
    dept_name           VARCHAR(100),
    dept_budget         NUMERIC(12, 2),
    -- embedded contract (denormalized)
    contract_type       VARCHAR(30),
    contract_start      DATE,
    contract_end        DATE,
    contract_status     VARCHAR(20) DEFAULT 'active',
    working_hours       INT DEFAULT 40,
    -- embedded evaluation scores (denormalized)
    score_technical     SMALLINT,
    score_leadership    SMALLINT,
    score_communication SMALLINT,
    score_teamwork      SMALLINT,
    score_initiative    SMALLINT,
    eval_overall        NUMERIC(2, 1),
    -- semi-structured metadata (JSONB)
    metadata            JSONB DEFAULT '{}',
    -- timestamps
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_denorm_dept_code    ON employees_denorm(dept_code);
CREATE INDEX idx_denorm_status       ON employees_denorm(status);
CREATE INDEX idx_denorm_salary       ON employees_denorm(salary_gross);
CREATE INDEX idx_denorm_hire_date    ON employees_denorm(hire_date);
CREATE INDEX idx_denorm_name         ON employees_denorm(last_name, first_name);
CREATE INDEX idx_denorm_contract_end ON employees_denorm(contract_end);
CREATE INDEX idx_denorm_metadata     ON employees_denorm USING GIN (metadata);
