"""
Load generator script for simulating PostgreSQL database activity.

Executes queries directly against PostgreSQL so that the database
generates real CSV log entries (log_statement = 'all').

Creates realistic workload patterns for different user types:
- OLTP transactions (business hours, frequent small queries)
- Night batch jobs (0-5 AM, heavy aggregations)
- Administrator actions (DDL operations, infrequent)
- Suspicious activity (unusual patterns for anomaly detection)
"""

import os
import sys
import time
import random
import time as time_module

# Add parent directory to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "etl"))

from sqlalchemy import text
from db_client import get_engine


# ---------------------------------------------------------------------------
# SQL query templates
# ---------------------------------------------------------------------------
SELECT_TEMPLATES = [
    "SELECT * FROM information_schema.tables WHERE table_schema = 'public'",
    "SELECT current_database(), current_user, session_user",
    "SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active'",
    "SELECT n.nspname, c.relname, c.reltuples FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'r' ORDER BY c.reltuples DESC LIMIT 20",
    "SELECT schemaname, tablename, indexname FROM pg_indexes WHERE schemaname = 'public'",
    "SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size",
    "SELECT datname, numbackends, xact_commit, xact_rollback FROM pg_stat_database",
]

DML_TEMPLATES = [
    "INSERT INTO gen_log (msg) VALUES ('Request processed at ' || now())",
    "INSERT INTO gen_audit (action, detail) VALUES ('login', 'user action logged')",
    "INSERT INTO gen_orders (user_id, product_id, total) VALUES (1, 2, 100.50)",
    "UPDATE gen_log SET msg = 'updated' WHERE id = 1",
    "DELETE FROM gen_log WHERE msg LIKE 'old%'",
]

DDL_TEMPLATES = [
    "CREATE TABLE IF NOT EXISTS gen_tmp_{val} (id INT, data TEXT)",
    "DROP TABLE IF EXISTS gen_tmp_{val}",
    "CREATE INDEX IF NOT EXISTS idx_gen_{val} ON gen_log(msg)",
]

ANALYST_TEMPLATES = [
    "SELECT schemaname, COUNT(*) AS table_count FROM pg_tables GROUP BY schemaname",
    "SELECT datname, blks_read, blks_hit, blks_hit::float / NULLIF(blks_read + blks_hit, 0) AS hit_ratio FROM pg_stat_database",
    "SELECT pid, state, wait_event_type, query_start FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start DESC LIMIT 50",
    "SELECT locktype, mode, granted, COUNT(*) FROM pg_locks GROUP BY 1, 2, 3 ORDER BY 4 DESC",
    "SELECT usename, COUNT(*) AS query_count FROM pg_stat_activity GROUP BY usename ORDER BY 2 DESC",
]

SUSPICIOUS_QUERIES = {
    "night_spike": [
        "SELECT * FROM information_schema.columns WHERE table_schema = 'pg_catalog'",
        "SELECT * FROM pg_authid",
    ],
    "unusual_access": [
        "SELECT * FROM pg_shadow",
        "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole FROM pg_roles",
    ],
    "ddl_storm": [
        "CREATE TABLE IF NOT EXISTS gen_storm_{val} (data TEXT)",
        "DROP TABLE IF EXISTS gen_storm_{val}",
    ],
    "long_query": [
        "SELECT COUNT(*) FROM pg_class c1 CROSS JOIN pg_class c2 CROSS JOIN pg_class c3",
    ],
    "role_violation": [
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC",
    ],
}

# Setup queries to create working tables
SETUP_QUERIES = [
    "CREATE TEMP TABLE IF NOT EXISTS gen_log (id SERIAL PRIMARY KEY, msg TEXT)",
    "CREATE TEMP TABLE IF NOT EXISTS gen_audit (action TEXT, detail TEXT)",
    "CREATE TEMP TABLE IF NOT EXISTS gen_orders (user_id INT, product_id INT, total NUMERIC)",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
FREQ_MAP = {"high": (10, 50), "medium": (5, 15), "low": (1, 3)}


def _pick(template_list):
    return random.choice(template_list)


def _fill(template, **kw):
    """Replace {val}, {val1}, {val2}, {val3} placeholders with random ints."""
    result = template
    result = result.replace("{val}", str(random.randint(1, 10000)))
    result = result.replace("{val1}", str(random.randint(1, 500)))
    result = result.replace("{val2}", str(random.randint(1, 200)))
    result = result.replace("{val3}", str(round(random.uniform(10, 5000), 2)))
    for k, v in kw.items():
        result = result.replace("{" + k + "}", str(v))
    return result


def _execute_safe(conn, query: str):
    """Execute a query via SQLAlchemy connection. Returns True on success."""
    try:
        conn.execute(text(query))
        conn.commit()
        return True
    except Exception as e:
        print(f"  ⚠ Query failed: {str(e)[:100]}")
        return False


def _sleep(seconds: float):
    if seconds > 0:
        time_module.sleep(seconds)


def _setup_tables(conn):
    """Create temporary working tables for DML/DDL simulation."""
    for q in SETUP_QUERIES:
        try:
            conn.execute(text(q))
            conn.commit()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Simulation functions
# ---------------------------------------------------------------------------
def simulate_oltp_workload(conn, total_queries=200):
    executed = 0
    for _ in range(total_queries):
        roll = random.random()
        if roll < 0.70:
            query = _fill(_pick(SELECT_TEMPLATES))
        else:
            query = _fill(_pick(DML_TEMPLATES))

        if _execute_safe(conn, query):
            executed += 1
        _sleep(random.uniform(0.001, 0.01))
    return executed


def simulate_analyst_queries(conn, total_queries=80):
    executed = 0
    for _ in range(total_queries):
        query = _pick(ANALYST_TEMPLATES)
        if _execute_safe(conn, query):
            executed += 1
        _sleep(random.uniform(0.01, 0.05))
    return executed


def simulate_admin_queries(conn, total_queries=30):
    executed = 0
    for _ in range(total_queries):
        roll = random.random()
        if roll < 0.30:
            query = _fill(_pick(SELECT_TEMPLATES))
        elif roll < 0.80:
            query = _fill(_pick(DDL_TEMPLATES))
        else:
            query = "GRANT SELECT ON ALL TABLES IN SCHEMA public TO PUBLIC"

        if _execute_safe(conn, query):
            executed += 1
        _sleep(random.uniform(0.05, 0.2))
    return executed


def simulate_night_jobs(conn, total_queries=200):
    executed = 0
    for _ in range(total_queries):
        roll = random.random()
        if roll < 0.70:
            query = _fill(_pick(SELECT_TEMPLATES))
        else:
            query = _fill(_pick(DML_TEMPLATES))

        if _execute_safe(conn, query):
            executed += 1
        _sleep(random.uniform(0.001, 0.01))
    return executed


def simulate_suspicious_activity(conn, total_queries=50):
    executed = 0
    anomaly_types = list(SUSPICIOUS_QUERIES.keys())

    for _ in range(total_queries):
        anomaly_type = random.choice(anomaly_types)
        query = random.choice(SUSPICIOUS_QUERIES[anomaly_type])
        query = _fill(query)

        if _execute_safe(conn, query):
            executed += 1
        _sleep(random.uniform(0.001, 0.01))
    return executed


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_load_simulation(duration_minutes=30):
    print("=" * 60)
    print("Load Simulation — Direct PostgreSQL Execution")
    print("=" * 60)
    print(f"  Target duration: ~{duration_minutes} min")
    print(f"  All queries logged to PostgreSQL CSV logs")
    print(f"  ETL will parse logs from PG_LOG_PATH")

    stats = {
        "oltp_count": 0,
        "analyst_count": 0,
        "admin_count": 0,
        "night_job_count": 0,
        "suspicious_count": 0,
        "total_queries": 0,
    }

    try:
        engine = get_engine()

        # Phase 1: OLTP
        print("\n[1/5] Executing OLTP workload...")
        n_queries = int(duration_minutes * 60 * 0.5)
        with engine.connect() as conn:
            _setup_tables(conn)
            stats["oltp_count"] = simulate_oltp_workload(conn, n_queries)
        print(f"  OLTP queries executed: {stats['oltp_count']}")

        # Phase 2: Analyst
        print("\n[2/5] Executing analyst queries...")
        n_queries = int(duration_minutes * 60 * 0.2)
        with engine.connect() as conn:
            stats["analyst_count"] = simulate_analyst_queries(conn, n_queries)
        print(f"  Analyst queries executed: {stats['analyst_count']}")

        # Phase 3: Admin
        print("\n[3/5] Executing admin operations...")
        n_queries = int(duration_minutes * 60 * 0.1)
        with engine.connect() as conn:
            stats["admin_count"] = simulate_admin_queries(conn, n_queries)
        print(f"  Admin queries executed: {stats['admin_count']}")

        # Phase 4: Night jobs
        print("\n[4/5] Executing night batch jobs...")
        n_queries = int(duration_minutes * 60 * 0.3)
        with engine.connect() as conn:
            _setup_tables(conn)
            stats["night_job_count"] = simulate_night_jobs(conn, n_queries)
        print(f"  Night job queries executed: {stats['night_job_count']}")

        # Phase 5: Suspicious activity
        print("\n[5/5] Injecting suspicious activity...")
        n_queries = int(duration_minutes * 60 * 0.1)
        with engine.connect() as conn:
            stats["suspicious_count"] = simulate_suspicious_activity(conn, n_queries)
        print(f"  Suspicious queries executed: {stats['suspicious_count']}")

    except Exception as e:
        print(f"\n  Fatal error: {e}")
        import traceback
        traceback.print_exc()

    stats["total_queries"] = sum(v for k, v in stats.items() if k != "total_queries")

    print("\n" + "=" * 60)
    print("Simulation Summary")
    print("=" * 60)
    print(f"  Total queries:     {stats['total_queries']}")
    print(f"  └ OLTP:            {stats['oltp_count']}")
    print(f"  └ Analyst:         {stats['analyst_count']}")
    print(f"  └ Admin:           {stats['admin_count']}")
    print(f"  └ Night jobs:      {stats['night_job_count']}")
    print(f"  └ Suspicious:      {stats['suspicious_count']}")
    print(f"\n  PostgreSQL CSV logs contain all executed queries.")
    print(f"  Run ETL pipeline to parse and load them.")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run load simulation against PostgreSQL")
    parser.add_argument(
        "--minutes",
        type=int,
        default=5,
        help="Approximate simulation duration in minutes",
    )
    args = parser.parse_args()

    stats = run_load_simulation(duration_minutes=args.minutes)
    print(f"\nDone! {stats['total_queries']} queries executed.")
    print("PostgreSQL CSV logs are ready for the ETL pipeline.")
