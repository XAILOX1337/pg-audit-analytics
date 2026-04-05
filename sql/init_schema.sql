-- ============================================================================
-- pg-audit-analytics: Complete Database Initialization Script
--
-- Purpose:
--   1. Create working tables for load generator (users, orders, etc.)
--   2. Create audit_data schema for analytics
--   3. Create roles for role-based audit testing
--   4. Create indexes, views, and helper functions
--
-- Usage (Windows, no Docker):
--   psql -U postgres -f sql/init_schema.sql
-- ============================================================================

-- ============================================================================
-- PART 1: WORKING TABLES (for load generator queries)
-- These tables receive actual queries from load_generator.py
-- Their activity is logged by PostgreSQL/pgAudit
-- ============================================================================

-- Users table: core application users
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    region          VARCHAR(50) DEFAULT 'default',
    role            VARCHAR(50) DEFAULT 'user',
    last_login      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Customers table: customer data for analyst queries
CREATE TABLE IF NOT EXISTS customers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    region          VARCHAR(50),
    phone           VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Products table: product catalog
CREATE TABLE IF NOT EXISTS products (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    price           NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    category        VARCHAR(100),
    stock_quantity  INTEGER DEFAULT 0 CHECK (stock_quantity >= 0),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Orders table: transactional data (high-volume, frequently queried)
CREATE TABLE IF NOT EXISTS orders (
    id              SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    product_id      INTEGER REFERENCES products(id) ON DELETE SET NULL,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    total           NUMERIC(12, 2) NOT NULL CHECK (total >= 0),
    status          VARCHAR(20) DEFAULT 'pending'
                        CHECK (status IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')),
    order_date      TIMESTAMPTZ DEFAULT NOW(),
    shipped_date    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Logs table: application logs (high INSERT volume)
CREATE TABLE IF NOT EXISTS logs (
    id              SERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    level           VARCHAR(10) DEFAULT 'INFO'
                        CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    message         TEXT NOT NULL,
    source          VARCHAR(200),
    processed       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Audit trail table: tracks user actions (meta-audit)
CREATE TABLE IF NOT EXISTS audit_trail (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(100) NOT NULL,
    target_table    VARCHAR(100),
    target_id       INTEGER,
    old_value       JSONB,
    new_value       JSONB,
    timestamp       TIMESTAMPTZ DEFAULT NOW(),
    ip_address      INET
);

-- Analytics table: aggregated metrics (analyst queries target this)
CREATE TABLE IF NOT EXISTS analytics (
    id              SERIAL PRIMARY KEY,
    metric_name     VARCHAR(100) NOT NULL,
    metric_value    NUMERIC(15, 4),
    dimension       VARCHAR(100),
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Sessions table: user sessions (DELETE target for cleanup jobs)
CREATE TABLE IF NOT EXISTS sessions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_token   VARCHAR(255) NOT NULL UNIQUE,
    ip_address      INET,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE
);

-- System configuration table (admin management target)
CREATE TABLE IF NOT EXISTS system_config (
    id              SERIAL PRIMARY KEY,
    config_key      VARCHAR(100) NOT NULL UNIQUE,
    config_value    JSONB,
    description     TEXT,
    updated_by      VARCHAR(100),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Temporary data table (night job cleanup target)
CREATE TABLE IF NOT EXISTS temp_data (
    id              SERIAL PRIMARY KEY,
    data            JSONB,
    source          VARCHAR(100),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN DEFAULT FALSE
);

-- ============================================================================
-- SEED DATA: Insert sample rows so queries return results
-- ============================================================================

INSERT INTO users (username, email, full_name, region, role) VALUES
    ('alice', 'alice@example.com', 'Alice Johnson', 'us-east', 'admin'),
    ('bob', 'bob@example.com', 'Bob Smith', 'eu-west', 'analyst'),
    ('charlie', 'charlie@example.com', 'Charlie Brown', 'us-west', 'user'),
    ('diana', 'diana@example.com', 'Diana Prince', 'ap-south', 'user'),
    ('etl_service', 'etl@internal.com', 'ETL Service Account', 'internal', 'service')
ON CONFLICT (username) DO NOTHING;

INSERT INTO customers (name, email, region, phone) VALUES
    ('Acme Corp', 'contact@acme.com', 'us-east', '+1-555-0100'),
    ('Globex Inc', 'info@globex.com', 'eu-west', '+44-20-7946-0958'),
    ('Initech', 'support@initech.com', 'us-west', '+1-555-0200'),
    ('Umbrella Co', 'sales@umbrella.com', 'ap-south', '+81-3-1234-5678'),
    ('Stark Industries', 'tony@stark.com', 'us-east', '+1-555-0300')
ON CONFLICT DO NOTHING;

INSERT INTO products (name, description, price, category, stock_quantity) VALUES
    ('Widget A', 'Standard widget', 29.99, 'widgets', 1000),
    ('Widget B', 'Premium widget', 49.99, 'widgets', 500),
    ('Gadget X', 'Multi-purpose gadget', 99.99, 'gadgets', 250),
    ('Gadget Y', 'Basic gadget', 59.99, 'gadgets', 750),
    ('Service Plan', 'Annual support plan', 199.99, 'services', 9999)
ON CONFLICT DO NOTHING;

INSERT INTO orders (customer_id, product_id, quantity, total, status, order_date) VALUES
    (1, 1, 5, 149.95, 'delivered', NOW() - INTERVAL '30 days'),
    (1, 3, 1, 99.99, 'shipped', NOW() - INTERVAL '7 days'),
    (2, 2, 10, 499.90, 'processing', NOW() - INTERVAL '2 days'),
    (3, 5, 1, 199.99, 'pending', NOW() - INTERVAL '1 day'),
    (4, 4, 3, 179.97, 'delivered', NOW() - INTERVAL '45 days'),
    (5, 1, 20, 599.80, 'shipped', NOW() - INTERVAL '3 days'),
    (2, 4, 2, 119.98, 'delivered', NOW() - INTERVAL '60 days'),
    (3, 3, 1, 99.99, 'cancelled', NOW() - INTERVAL '15 days')
ON CONFLICT DO NOTHING;

INSERT INTO system_config (config_key, config_value, description, updated_by) VALUES
    ('max_connections', '100', 'Maximum database connections', 'admin'),
    ('log_retention_days', '30', 'Days to keep audit logs', 'admin'),
    ('batch_size', '1000', 'Default batch processing size', 'admin'),
    ('maintenance_window', '{"start": "02:00", "end": "04:00"}', 'Scheduled maintenance window', 'admin')
ON CONFLICT (config_key) DO NOTHING;

-- ============================================================================
-- PART 2: AUDIT_DATA SCHEMA (Analytics storage)
-- This schema holds parsed and aggregated audit data
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS audit_data;

COMMENT ON SCHEMA audit_data IS
    'Schema for PostgreSQL audit log analytics — parsed logs, aggregations, and ML results';


-- ============================================================================
-- TABLE: audit_data.audit_logs
-- Purpose: Raw parsed audit log entries from PostgreSQL CSV logs
-- Source: ETL pipeline (etl/parser.py → etl/loader.py)
-- ============================================================================

CREATE TABLE audit_data.audit_logs (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL,
    username            VARCHAR(100) NOT NULL,
    database_name       VARCHAR(100),
    operation_type      VARCHAR(20) NOT NULL,
    operation_category  VARCHAR(10) NOT NULL,
    table_name          VARCHAR(200),
    duration_ms         NUMERIC(10, 3),
    raw_query           TEXT,
    query_hash          VARCHAR(64),
    session_id          VARCHAR(100),
    application_name    VARCHAR(200),
    created_at          TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT chk_audit_logs_operation_type
        CHECK (operation_type IN (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE',
            'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
            'GRANT', 'REVOKE'
        )),
    CONSTRAINT chk_audit_logs_operation_category
        CHECK (operation_category IN ('READ', 'WRITE', 'DDL', 'DCL')),
    CONSTRAINT chk_audit_logs_duration_non_negative
        CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

COMMENT ON TABLE audit_data.audit_logs IS
    'Raw parsed PostgreSQL audit log entries from CSV log files';

COMMENT ON COLUMN audit_data.audit_logs.query_hash IS
    'SHA-256 hash of normalized query for deduplication and pattern matching';


-- ============================================================================
-- TABLE: audit_data.user_activity
-- Purpose: Pre-aggregated user behavior by hour, day, and operation type
-- Source: ETL aggregation (etl/loader.py → aggregate_user_activity())
-- Used by: Clustering algorithm (analytics/clustering.py)
-- ============================================================================

CREATE TABLE audit_data.user_activity (
    id                  BIGSERIAL PRIMARY KEY,
    username            VARCHAR(100) NOT NULL,
    hour_of_day         SMALLINT NOT NULL,
    day_of_week         SMALLINT NOT NULL,
    operation_type      VARCHAR(20) NOT NULL,
    operation_category  VARCHAR(10) NOT NULL,
    query_count         INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms     NUMERIC(10, 3),
    total_duration_ms   NUMERIC(12, 3),
    unique_tables       INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    -- Unique constraint for upsert logic
    CONSTRAINT uq_user_activity
        UNIQUE (username, hour_of_day, day_of_week, operation_type),

    -- Range constraints
    CONSTRAINT chk_user_activity_hour
        CHECK (hour_of_day BETWEEN 0 AND 23),
    CONSTRAINT chk_user_activity_day
        CHECK (day_of_week BETWEEN 0 AND 6),
    CONSTRAINT chk_user_activity_count
        CHECK (query_count >= 0),
    CONSTRAINT chk_user_activity_tables
        CHECK (unique_tables >= 0)
);

COMMENT ON TABLE audit_data.user_activity IS
    'Aggregated user activity by hour/day/operation — input for clustering';


-- ============================================================================
-- TABLE: audit_data.query_stats
-- Purpose: Query performance statistics grouped by pattern
-- Source: ETL aggregation (etl/loader.py → compute_query_stats())
-- Used by: Query analysis (analytics/query_analysis.py)
-- ============================================================================

CREATE TABLE audit_data.query_stats (
    id                  BIGSERIAL PRIMARY KEY,
    query_pattern       TEXT NOT NULL,
    query_hash          VARCHAR(64) NOT NULL UNIQUE,
    operation_type      VARCHAR(20) NOT NULL,
    table_name          VARCHAR(200),
    execution_count     INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms     NUMERIC(10, 3) NOT NULL,
    min_duration_ms     NUMERIC(10, 3),
    max_duration_ms     NUMERIC(10, 3),
    p50_duration_ms     NUMERIC(10, 3),
    p95_duration_ms     NUMERIC(10, 3),
    p99_duration_ms     NUMERIC(10, 3),
    first_seen          TIMESTAMPTZ NOT NULL,
    last_seen           TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chk_query_stats_count
        CHECK (execution_count >= 0),
    CONSTRAINT chk_query_stats_avg
        CHECK (avg_duration_ms >= 0)
);

COMMENT ON TABLE audit_data.query_stats IS
    'Query performance statistics grouped by normalized query pattern';


-- ============================================================================
-- TABLE: audit_data.anomaly_results
-- Purpose: Detected anomalies from ML and rule-based detection
-- Source: Anomaly detection (analytics/anomaly_detection.py)
-- ============================================================================

CREATE TABLE audit_data.anomaly_results (
    id              BIGSERIAL PRIMARY KEY,
    timestamp       TIMESTAMPTZ NOT NULL,
    anomaly_type    VARCHAR(50) NOT NULL,
    severity        VARCHAR(10) NOT NULL,
    username        VARCHAR(100),
    description     TEXT,
    metrics         JSONB,
    score           NUMERIC(10, 5),
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chk_anomaly_severity
        CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH')),
    CONSTRAINT chk_anomaly_type
        CHECK (anomaly_type IN (
            'isolation_forest', 'lof', 'rule_based',
            'night_spike', 'unusual_access', 'ddl_storm',
            'long_query', 'role_violation'
        ))
);

COMMENT ON TABLE audit_data.anomaly_results IS
    'Detected anomalies from Isolation Forest, LOF, and rule-based checks';

COMMENT ON COLUMN audit_data.anomaly_results.metrics IS
    'JSONB blob with detailed metrics at time of anomaly detection';


-- ============================================================================
-- TABLE: audit_data.clustering_results
-- Purpose: User cluster assignments from KMeans and DBSCAN
-- Source: Clustering (analytics/clustering.py)
-- ============================================================================

CREATE TABLE audit_data.clustering_results (
    id              BIGSERIAL PRIMARY KEY,
    username        VARCHAR(100) NOT NULL,
    cluster_id      INTEGER NOT NULL,
    cluster_label   VARCHAR(50),
    algorithm       VARCHAR(20) NOT NULL,
    features        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT chk_clustering_algorithm
        CHECK (algorithm IN ('kmeans', 'dbscan')),
    CONSTRAINT uq_clustering_user_algo
        UNIQUE (username, algorithm)
);

COMMENT ON TABLE audit_data.clustering_results IS
    'User cluster assignments with semantic labels (Night Jobs, OLTP, Admin, etc.)';

COMMENT ON COLUMN audit_data.clustering_results.features IS
    'JSONB feature vector used for clustering (for reproducibility)';


-- ============================================================================
-- PART 3: INDEXES
-- ============================================================================

-- audit_logs indexes
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp
    ON audit_data.audit_logs (timestamp);

CREATE INDEX IF NOT EXISTS idx_audit_logs_username
    ON audit_data.audit_logs (username);

CREATE INDEX IF NOT EXISTS idx_audit_logs_operation_type
    ON audit_data.audit_logs (operation_type);

CREATE INDEX IF NOT EXISTS idx_audit_logs_operation_category
    ON audit_data.audit_logs (operation_category);

CREATE INDEX IF NOT EXISTS idx_audit_logs_table_name
    ON audit_data.audit_logs (table_name);

CREATE INDEX IF NOT EXISTS idx_audit_logs_query_hash
    ON audit_data.audit_logs (query_hash);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_time
    ON audit_data.audit_logs (username, timestamp);

-- user_activity indexes
CREATE INDEX IF NOT EXISTS idx_user_activity_username
    ON audit_data.user_activity (username);

CREATE INDEX IF NOT EXISTS idx_user_activity_hour
    ON audit_data.user_activity (hour_of_day);

CREATE INDEX IF NOT EXISTS idx_user_activity_category
    ON audit_data.user_activity (operation_category);

CREATE INDEX IF NOT EXISTS idx_user_activity_hour_category
    ON audit_data.user_activity (hour_of_day, operation_category);

-- query_stats indexes
CREATE INDEX IF NOT EXISTS idx_query_stats_query_hash
    ON audit_data.query_stats (query_hash);

CREATE INDEX IF NOT EXISTS idx_query_stats_operation_type
    ON audit_data.query_stats (operation_type);

CREATE INDEX IF NOT EXISTS idx_query_stats_table_name
    ON audit_data.query_stats (table_name);

CREATE INDEX IF NOT EXISTS idx_query_stats_avg_duration
    ON audit_data.query_stats (avg_duration_ms DESC);

-- anomaly_results indexes
CREATE INDEX IF NOT EXISTS idx_anomaly_timestamp
    ON audit_data.anomaly_results (timestamp);

CREATE INDEX IF NOT EXISTS idx_anomaly_severity
    ON audit_data.anomaly_results (severity);

CREATE INDEX IF NOT EXISTS idx_anomaly_username
    ON audit_data.anomaly_results (username);

CREATE INDEX IF NOT EXISTS idx_anomaly_time_severity
    ON audit_data.anomaly_results (timestamp, severity);

-- clustering_results indexes
CREATE INDEX IF NOT EXISTS idx_clustering_username
    ON audit_data.clustering_results (username);

CREATE INDEX IF NOT EXISTS idx_clustering_algorithm
    ON audit_data.clustering_results (algorithm);

CREATE INDEX IF NOT EXISTS idx_clustering_label
    ON audit_data.clustering_results (cluster_label);


-- ============================================================================
-- PART 4: VIEWS
-- ============================================================================

-- View: User activity summary
CREATE OR REPLACE VIEW audit_data.user_activity_summary AS
SELECT
    username,
    SUM(query_count) AS total_queries,
    ROUND(AVG(avg_duration_ms), 2) AS overall_avg_duration_ms,
    SUM(total_duration_ms) AS total_duration_ms,
    COUNT(DISTINCT hour_of_day) AS active_hours_count,
    COUNT(DISTINCT operation_category) AS operation_types_used,
    MIN(hour_of_day) AS earliest_active_hour,
    MAX(hour_of_day) AS latest_active_hour
FROM audit_data.user_activity
GROUP BY username;

-- View: Hourly activity heatmap data
CREATE OR REPLACE VIEW audit_data.hourly_activity_heatmap AS
SELECT
    hour_of_day,
    operation_category,
    SUM(query_count) AS total_queries,
    COUNT(DISTINCT username) AS active_users,
    ROUND(AVG(avg_duration_ms), 2) AS avg_duration_ms
FROM audit_data.user_activity
GROUP BY hour_of_day, operation_category
ORDER BY hour_of_day, operation_category;

-- View: Top queried tables
CREATE OR REPLACE VIEW audit_data.top_queried_tables AS
SELECT
    table_name,
    COUNT(*) AS query_count,
    COUNT(DISTINCT username) AS unique_users,
    ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
    MAX(duration_ms) AS max_duration_ms,
    operation_category,
    DATE_TRUNC('hour', timestamp) AS hour_bucket
FROM audit_data.audit_logs
WHERE table_name IS NOT NULL
GROUP BY table_name, operation_category, DATE_TRUNC('hour', timestamp);

-- View: Slow queries
CREATE OR REPLACE VIEW audit_data.slow_queries AS
SELECT
    al.id,
    al.timestamp,
    al.username,
    al.operation_type,
    al.table_name,
    al.duration_ms,
    al.raw_query,
    qs.p95_duration_ms AS p95_threshold,
    ROUND(
        ((al.duration_ms - qs.p95_duration_ms) / NULLIF(qs.p95_duration_ms, 0)) * 100,
        1
    ) AS pct_above_p95
FROM audit_data.audit_logs al
LEFT JOIN audit_data.query_stats qs ON al.query_hash = qs.query_hash
WHERE al.duration_ms IS NOT NULL
  AND qs.p95_duration_ms IS NOT NULL
  AND al.duration_ms > qs.p95_duration_ms
ORDER BY al.duration_ms DESC;

-- View: User operation mix
CREATE OR REPLACE VIEW audit_data.user_operation_mix AS
SELECT
    username,
    operation_category,
    SUM(query_count) AS total_operations,
    ROUND(
        SUM(query_count) * 100.0 / NULLIF(SUM(SUM(query_count)) OVER (PARTITION BY username), 0),
        1
    ) AS percentage
FROM audit_data.user_activity
GROUP BY username, operation_category;

-- View: Anomaly timeline
CREATE OR REPLACE VIEW audit_data.anomaly_timeline AS
SELECT
    DATE_TRUNC('hour', timestamp) AS hour_bucket,
    COUNT(*) AS anomaly_count,
    COUNT(*) FILTER (WHERE severity = 'HIGH') AS high_severity_count,
    COUNT(*) FILTER (WHERE severity = 'MEDIUM') AS medium_severity_count,
    COUNT(*) FILTER (WHERE severity = 'LOW') AS low_severity_count,
    ARRAY_AGG(DISTINCT anomaly_type) AS anomaly_types,
    ARRAY_AGG(DISTINCT username) FILTER (WHERE username IS NOT NULL) AS affected_users
FROM audit_data.anomaly_results
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY hour_bucket;

-- View: Daily activity summary
CREATE OR REPLACE VIEW audit_data.daily_activity AS
SELECT
    DATE(timestamp) AS activity_date,
    EXTRACT(DOW FROM timestamp)::INTEGER AS day_of_week,
    COUNT(*) AS total_queries,
    COUNT(DISTINCT username) AS unique_users,
    ROUND(AVG(duration_ms), 2) AS avg_duration_ms,
    COUNT(*) FILTER (WHERE operation_category = 'DDL') AS ddl_count,
    COUNT(*) FILTER (WHERE operation_category = 'WRITE') AS write_count,
    COUNT(*) FILTER (WHERE operation_category = 'READ') AS read_count
FROM audit_data.audit_logs
GROUP BY DATE(timestamp), EXTRACT(DOW FROM timestamp)
ORDER BY activity_date;


-- ============================================================================
-- PART 5: HELPER FUNCTIONS
-- ============================================================================

-- Function: Compute query hash
CREATE OR REPLACE FUNCTION audit_data.compute_query_hash(query_text TEXT)
RETURNS VARCHAR(64)
LANGUAGE sql
IMMUTABLE
AS $func$
    SELECT encode(
        sha256(
            regexp_replace(
                regexp_replace(lower(trim(query_text)), $$'[^'']*'$$, '?', 'g'),
                '\d+',
                '?',
                'g'
            )::bytea
        ),
        'hex'
    );
$func$;

-- Function: Classify operation type into category
CREATE OR REPLACE FUNCTION audit_data.classify_operation(op_type VARCHAR)
RETURNS VARCHAR(10)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE op_type
        WHEN 'SELECT' THEN 'READ'
        WHEN 'INSERT' THEN 'WRITE'
        WHEN 'UPDATE' THEN 'WRITE'
        WHEN 'DELETE' THEN 'WRITE'
        WHEN 'CREATE' THEN 'DDL'
        WHEN 'ALTER'  THEN 'DDL'
        WHEN 'DROP'   THEN 'DDL'
        WHEN 'TRUNCATE' THEN 'DDL'
        WHEN 'GRANT'  THEN 'DCL'
        WHEN 'REVOKE' THEN 'DCL'
        ELSE 'OTHER'
    END;
$$;

-- Function: Refresh user activity aggregation
CREATE OR REPLACE FUNCTION audit_data.refresh_user_activity()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit_data.user_activity (
        username, hour_of_day, day_of_week,
        operation_type, operation_category,
        query_count, avg_duration_ms, total_duration_ms, unique_tables
    )
    SELECT
        username,
        EXTRACT(HOUR FROM timestamp)::SMALLINT AS hour_of_day,
        EXTRACT(DOW FROM timestamp)::SMALLINT AS day_of_week,
        operation_type,
        operation_category,
        COUNT(*) AS query_count,
        ROUND(AVG(duration_ms), 3) AS avg_duration_ms,
        ROUND(SUM(duration_ms), 3) AS total_duration_ms,
        COUNT(DISTINCT table_name) AS unique_tables
    FROM audit_data.audit_logs
    GROUP BY
        username,
        EXTRACT(HOUR FROM timestamp),
        EXTRACT(DOW FROM timestamp),
        operation_type,
        operation_category
    ON CONFLICT (username, hour_of_day, day_of_week, operation_type)
    DO UPDATE SET
        query_count = EXCLUDED.query_count,
        avg_duration_ms = EXCLUDED.avg_duration_ms,
        total_duration_ms = EXCLUDED.total_duration_ms,
        unique_tables = EXCLUDED.unique_tables,
        updated_at = NOW();
END;
$$;


-- ============================================================================
-- PART 6: ROLES (For role-based audit testing)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin') THEN
        CREATE ROLE admin WITH LOGIN PASSWORD 'admin_password' SUPERUSER;
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_password' NOSUPERUSER;
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst') THEN
        CREATE ROLE analyst WITH LOGIN PASSWORD 'analyst_password' NOSUPERUSER;
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'night_job') THEN
        CREATE ROLE night_job WITH LOGIN PASSWORD 'night_password' NOSUPERUSER;
    END IF;
END
$$;

-- ============================================================================
-- PART 7: PERMISSIONS
-- ============================================================================

GRANT USAGE ON SCHEMA audit_data TO app_user, analyst, night_job;
GRANT ALL ON SCHEMA audit_data TO admin;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO night_job;
GRANT ALL ON ALL TABLES IN SCHEMA public TO admin;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO night_job;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO admin;

GRANT SELECT ON ALL TABLES IN SCHEMA audit_data TO analyst;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA audit_data TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit_data TO app_user;

GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA audit_data TO night_job;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA audit_data TO night_job;

GRANT ALL ON ALL TABLES IN SCHEMA audit_data TO admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA audit_data TO admin;

GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit_data TO analyst;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit_data TO app_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA audit_data TO night_job;

ALTER DEFAULT PRIVILEGES IN SCHEMA audit_data
    GRANT SELECT ON TABLES TO analyst;

ALTER DEFAULT PRIVILEGES IN SCHEMA audit_data
    GRANT SELECT, INSERT, UPDATE ON TABLES TO app_user, night_job;

ALTER DEFAULT PRIVILEGES IN SCHEMA audit_data
    GRANT ALL ON TABLES TO admin;


-- ============================================================================
-- PART 8: VERIFICATION
-- ============================================================================

DO $$
DECLARE
    table_count INTEGER;
    view_count INTEGER;
    index_count INTEGER;
    role_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO table_count
    FROM information_schema.tables
    WHERE table_schema = 'audit_data' AND table_type = 'BASE TABLE';

    SELECT COUNT(*) INTO view_count
    FROM information_schema.views
    WHERE table_schema = 'audit_data';

    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'audit_data';

    SELECT COUNT(*) INTO role_count
    FROM pg_roles
    WHERE rolname IN ('admin', 'app_user', 'analyst', 'night_job');

    RAISE NOTICE '============================================';
    RAISE NOTICE ' pg-audit-analytics: Database Initialized';
    RAISE NOTICE '============================================';
    RAISE NOTICE ' Working tables (public): 9';
    RAISE NOTICE ' Audit tables: %', table_count;
    RAISE NOTICE ' Views: %', view_count;
    RAISE NOTICE ' Indexes: %', index_count;
    RAISE NOTICE ' Roles configured: %', role_count;
    RAISE NOTICE '============================================';
    RAISE NOTICE ' Ready for load generation and ETL pipeline';
    RAISE NOTICE '============================================';
END
$$;
