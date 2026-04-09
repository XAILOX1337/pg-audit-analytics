"""
Load generator script for simulating PostgreSQL database activity.

Creates realistic workload patterns for different user types:
- OLTP transactions (business hours, frequent small queries)
- Night batch jobs (0-5 AM, heavy aggregations)
- Administrator actions (DDL operations, infrequent)
- Suspicious activity (unusual patterns for anomaly detection)
"""

import os
import sys
import csv
import random
import uuid
from datetime import datetime, timedelta

# Add parent directory to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "etl"))

from config import RAW_LOGS_DIR
from db_client import get_connection, execute_query

RAW_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# SQL query templates
# ---------------------------------------------------------------------------
SELECT_TEMPLATES = [
    "SELECT * FROM users WHERE id = {val}",
    "SELECT name, email FROM customers WHERE region = 'region_{val}'",
    "SELECT COUNT(*) FROM orders WHERE date > '2025-01-01'",
    "SELECT p.name, o.total FROM products p JOIN orders o ON p.id = o.product_id WHERE o.status = 'active'",
    "SELECT u.username, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.username",
    "SELECT * FROM logs WHERE level = 'ERROR' AND created_at > '2025-06-01' ORDER BY created_at DESC LIMIT 100",
    "SELECT AVG(total), MAX(total) FROM orders WHERE user_id = {val}",
]

INSERT_TEMPLATES = [
    "INSERT INTO logs (timestamp, message, level) VALUES (NOW(), 'Request processed', 'INFO')",
    "INSERT INTO audit_trail (user_id, action, timestamp) VALUES ({val}, 'login', NOW())",
    "INSERT INTO orders (user_id, product_id, total, status) VALUES ({val1}, {val2}, {val3}, 'pending')",
]

UPDATE_TEMPLATES = [
    "UPDATE users SET last_login = NOW() WHERE id = {val}",
    "UPDATE orders SET status = 'shipped' WHERE id = {val}",
    "UPDATE products SET price = price * 1.1 WHERE category = 'electronics'",
]

DELETE_TEMPLATES = [
    "DELETE FROM temp_data WHERE created_at < NOW() - INTERVAL '7 days'",
    "DELETE FROM sessions WHERE expires_at < NOW()",
    "DELETE FROM logs WHERE level = 'DEBUG' AND created_at < NOW() - INTERVAL '30 days'",
]

DDL_TEMPLATES = [
    "CREATE TABLE IF NOT EXISTS temp_table_{val} (id INT PRIMARY KEY, data TEXT)",
    "ALTER TABLE logs ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE",
    "DROP TABLE IF EXISTS temp_table_{val}",
    "CREATE INDEX IF NOT EXISTS idx_orders_user_{val} ON orders(user_id)",
]

ANALYST_TEMPLATES = [
    "SELECT DATE_TRUNC('day', o.created_at) AS day, COUNT(*) FROM orders o GROUP BY 1 ORDER BY 1",
    "SELECT u.region, SUM(o.total) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.region",
    "SELECT product_id, AVG(total) FROM orders GROUP BY product_id HAVING COUNT(*) > 10 ORDER BY 2 DESC",
    "SELECT EXTRACT(HOUR FROM created_at) AS h, COUNT(*) FROM orders GROUP BY h ORDER BY h",
    "WITH monthly AS (SELECT DATE_TRUNC('month', created_at) m, total FROM orders) SELECT m, SUM(total) FROM monthly GROUP BY 1",
]

SUSPICIOUS_TEMPLATES = [
    ("night_spike", "SELECT * FROM financial_records WHERE amount > 10000"),
    ("unusual_access", "SELECT * FROM salaries WHERE department = 'executive'"),
    ("ddl_storm", "CREATE TABLE audit_bypass_{val} (data TEXT)"),
    ("long_query", "SELECT COUNT(*) FROM orders o1 CROSS JOIN orders o2 CROSS JOIN orders o3"),
    ("role_violation", "DELETE FROM users WHERE role = 'admin'"),
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


def _cmd_tag(query: str) -> str:
    q = query.strip().upper()
    for tag in ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "TRUNCATE", "COPY"):
        if q.startswith(tag):
            return tag
    return "SELECT"


def _timestamp(base: datetime, offset_minutes: float) -> datetime:
    return base + timedelta(minutes=offset_minutes)


# ---------------------------------------------------------------------------
# Simulation functions
# ---------------------------------------------------------------------------
def simulate_oltp_workload(duration_minutes=60):
    """
    Simulate OLTP transaction workload.

    Characteristics:
    - High frequency: 10-50 queries per minute
    - Business hours: 8 AM - 6 PM
    - Operations: 60% SELECT, 30% INSERT, 10% UPDATE
    - Tables: users, orders, products, logs

    Args:
        duration_minutes (int): Simulation duration

    Returns:
        list[tuple]: (timestamp, username, query) records
    """
    records = []
    base = datetime(2026, 4, 6, 8, 0, 0)  # fixed start for reproducibility

    for minute in range(duration_minutes):
        qpm = random.randint(*FREQ_MAP["high"])
        for _ in range(qpm):
            roll = random.random()
            if roll < 0.60:
                query = _fill(_pick(SELECT_TEMPLATES))
            elif roll < 0.90:
                query = _fill(_pick(INSERT_TEMPLATES))
            else:
                query = _fill(_pick(UPDATE_TEMPLATES))

            ts = _timestamp(base, minute + random.uniform(0, 1))
            records.append((ts, "app_user", query))

    return records


def simulate_analyst_queries(duration_minutes=60):
    """
    Simulate analyst query workload.

    Characteristics:
    - Medium frequency: 5-15 queries per minute
    - Complex queries: JOINs, GROUP BY, subqueries
    - Business hours: 9 AM - 5 PM
    - Longer duration: 100-5000ms

    Args:
        duration_minutes (int): Simulation duration

    Returns:
        list[tuple]: (timestamp, username, query, duration_ms) records
    """
    records = []
    base = datetime(2026, 4, 6, 9, 0, 0)

    for minute in range(duration_minutes):
        qpm = random.randint(*FREQ_MAP["medium"])
        for _ in range(qpm):
            query = _pick(ANALYST_TEMPLATES)
            ts = _timestamp(base, minute + random.uniform(0, 1))
            duration = random.uniform(100, 5000)
            records.append((ts, "analyst", query, duration))

    return records


def simulate_admin_queries(duration_minutes=60):
    """
    Simulate administrator DDL workload.

    Characteristics:
    - Low frequency: 1-3 operations per minute
    - Operations: CREATE, ALTER, DROP, GRANT, REVOKE
    - Work hours: 10 AM - 4 PM
    - Targets: system tables, configurations, permissions

    Args:
        duration_minutes (int): Simulation duration

    Returns:
        list[tuple]: (timestamp, username, query) records
    """
    records = []
    base = datetime(2026, 4, 6, 10, 0, 0)

    for minute in range(duration_minutes):
        qpm = random.randint(*FREQ_MAP["low"])
        for _ in range(qpm):
            roll = random.random()
            if roll < 0.30:
                query = _fill(_pick(SELECT_TEMPLATES))
            elif roll < 0.80:
                query = _fill(_pick(DDL_TEMPLATES))
            else:
                query = f"GRANT SELECT ON TABLE users TO analyst_{random.randint(1, 5)}"

            ts = _timestamp(base, minute + random.uniform(0, 1))
            records.append((ts, "admin", query))

    return records


def simulate_night_jobs(duration_minutes=60):
    """
    Simulate night batch job workload.

    Characteristics:
    - High frequency during night: 0-5 AM, 10 PM - 12 AM
    - Operations: 70% SELECT, 20% INSERT, 10% DELETE
    - Patterns: ETL, aggregations, cleanup
    - Long-running queries: 500-10000ms

    Args:
        duration_minutes (int): Simulation duration

    Returns:
        list[tuple]: (timestamp, username, query, duration_ms) records
    """
    records = []
    base = datetime(2026, 4, 6, 0, 0, 0)  # starts at midnight

    for minute in range(duration_minutes):
        qpm = random.randint(*FREQ_MAP["high"])
        for _ in range(qpm):
            roll = random.random()
            if roll < 0.70:
                query = _fill(_pick(SELECT_TEMPLATES))
            elif roll < 0.90:
                query = _fill(_pick(INSERT_TEMPLATES))
            else:
                query = _fill(_pick(DELETE_TEMPLATES))

            ts = _timestamp(base, minute + random.uniform(0, 1))
            duration = random.uniform(500, 10000)
            records.append((ts, "night_job", query, duration))

    return records


def simulate_suspicious_activity(duration_minutes=60):
    """
    Simulate suspicious activity for anomaly detection testing.

    Injected anomalies:
    1. Night activity spike: Burst of 100+ queries at 3 AM
    2. Unusual table access: Admin accessing financial tables
    3. DDL storm: 20+ CREATE/ALTER operations in 5 minutes
    4. Long queries: Queries taking 30+ seconds
    5. Role violation: Read-only user executing DELETEs

    Args:
        duration_minutes (int): Simulation duration

    Returns:
        list[tuple]: (timestamp, username, query, anomaly_type) records
    """
    records = []
    base = datetime(2026, 4, 6, 3, 0, 0)  # 3 AM spike window

    # 1. Night activity spike at 3 AM
    for i in range(120):
        ts = _timestamp(base, random.uniform(0, 5))
        query = _fill(_pick(SELECT_TEMPLATES))
        records.append((ts, "app_user", query, "night_spike"))

    # 2. Unusual table access (admin hitting financial tables)
    for i in range(20):
        ts = _timestamp(base, random.uniform(0, duration_minutes))
        query = _fill(SUSPICIOUS_TEMPLATES[1][1])
        records.append((ts, "admin", query, "unusual_access"))

    # 3. DDL storm
    for i in range(30):
        ts = _timestamp(base, random.uniform(10, 15))
        query = _fill(_pick(DDL_TEMPLATES))
        records.append((ts, "admin", query, "ddl_storm"))

    # 4. Long queries
    for i in range(10):
        ts = _timestamp(base, random.uniform(0, duration_minutes))
        query = SUSPICIOUS_TEMPLATES[3][1]
        records.append((ts, "analyst", query, "long_query"))

    # 5. Role violation
    for i in range(15):
        ts = _timestamp(base, random.uniform(0, duration_minutes))
        query = SUSPICIOUS_TEMPLATES[4][1]
        records.append((ts, "analyst", query, "role_violation"))

    return records


# ---------------------------------------------------------------------------
# CSV log generation
# ---------------------------------------------------------------------------
def generate_csv_log(records, filename="simulated_log.csv"):
    """
    Generate PostgreSQL CSV log file from simulated records.

    Format matches PostgreSQL csvlog output:
    timestamp,username,database,process_id,connection_source,
    session_id,line_number,command_tag,session_start_time,
    virtual_transaction_id,transaction_id,error_severity,
    sql_state_code,message,detail,hint,internal_query,
    internal_query_pos,context,query,query_pos,location,application_name

    Args:
        records (list[tuple]): Simulated activity records
        filename (str): Output CSV filename
    """
    output_path = RAW_LOGS_DIR / filename

    session_ids = {}
    line_counter = 0

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        for rec in records:
            ts = rec[0]
            user = rec[1]
            query = rec[2]

            # Ensure each user has a consistent session_id
            if user not in session_ids:
                session_ids[user] = f"{uuid.uuid4().hex[:8]}.{uuid.uuid4().hex[:4]}"

            line_counter += 1
            cmd = _cmd_tag(query)
            pid = random.randint(1000, 65000)
            vtid = f"{random.randint(1,9)}/{random.randint(1000,99999)}"
            xid = random.randint(100000, 999999)

            # PostgreSQL CSV log line (22 fields + optional application_name)
            writer.writerow([
                ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " MSK",  # log_time
                user,                                                # user_name
                "postgres",                                          # database_name
                str(pid),                                            # process_id
                "",                                                  # connection_from
                session_ids[user],                                   # session_id
                str(line_counter),                                   # session_line_num
                cmd,                                                 # command_tag
                ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " MSK",  # session_start_time
                vtid,                                                # virtual_transaction_id
                str(xid),                                            # transaction_id
                "LOG",                                               # error_severity
                "00000",                                             # sql_state_code
                f"statement: {query}",                               # message
                "",                                                  # detail
                "",                                                  # hint
                "",                                                  # internal_query
                "",                                                  # internal_query_pos
                "",                                                  # context
                "",                                                  # location
                "python-app",                                        # application_name
                "",                                                  # backend_type
            ])

    print(f"  CSV log written to {output_path} ({line_counter} lines)")
    return str(output_path)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def run_load_simulation(duration_hours=24):
    """
    Execute complete load simulation.

    Pipeline:
    1. Simulate OLTP workload (40% of activity)
    2. Simulate analyst queries (20%)
    3. Simulate admin operations (10%)
    4. Simulate night jobs (20%)
    5. Inject suspicious activity (10%)
    6. Generate CSV log file in data/raw_logs/
    7. Print summary statistics

    Args:
        duration_hours (int): Simulation duration in hours

    Returns:
        dict: {
            'total_queries': int,
            'normal_queries': int,
            'suspicious_queries': int,
            'log_file': str
        }
    """
    print("=" * 60)
    print("Load Simulation")
    print("=" * 60)
    print(f"  Duration: {duration_hours}h, Start: 2026-04-06")

    minutes = duration_hours * 60

    # Step 1: OLTP
    print("\n[1/5] Simulating OLTP workload...")
    oltp = simulate_oltp_workload(minutes)
    print(f"  OLTP records: {len(oltp)}")

    # Step 2: Analyst
    print("\n[2/5] Simulating analyst queries...")
    analyst = simulate_analyst_queries(minutes)
    print(f"  Analyst records: {len(analyst)}")

    # Step 3: Admin
    print("\n[3/5] Simulating admin operations...")
    admin = simulate_admin_queries(minutes)
    print(f"  Admin records: {len(admin)}")

    # Step 4: Night jobs
    print("\n[4/5] Simulating night batch jobs...")
    night = simulate_night_jobs(minutes)
    print(f"  Night job records: {len(night)}")

    # Step 5: Suspicious activity
    print("\n[5/5] Injecting suspicious activity...")
    suspicious = simulate_suspicious_activity(minutes)
    print(f"  Suspicious records: {len(suspicious)}")

    # Combine all records
    all_records = []
    normal_count = 0
    suspicious_count = 0

    # Normal records: (ts, user, query)
    for r in oltp + admin:
        all_records.append((r[0], r[1], r[2]))
        normal_count += 1

    # Analyst/night with duration: strip duration for CSV
    for r in analyst + night:
        all_records.append((r[0], r[1], r[2]))
        normal_count += 1

    # Suspicious: strip anomaly_type
    for r in suspicious:
        all_records.append((r[0], r[1], r[2]))
        suspicious_count += 1

    # Sort by timestamp
    all_records.sort(key=lambda x: x[0])

    total = normal_count + suspicious_count

    # Generate CSV log
    print(f"\n  Generating CSV log ({total} records)...")
    log_file = generate_csv_log(all_records, filename="pg_audit_simulation.csv")

    stats = {
        "total_queries": total,
        "normal_queries": normal_count,
        "suspicious_queries": suspicious_count,
        "oltp_count": len(oltp),
        "analyst_count": len(analyst),
        "admin_count": len(admin),
        "night_job_count": len(night),
        "log_file": log_file,
    }

    print("\n" + "=" * 60)
    print("Simulation Summary")
    print("=" * 60)
    print(f"  Total queries:     {stats['total_queries']}")
    print(f"  Normal:            {stats['normal_queries']}")
    print(f"  Suspicious:        {stats['suspicious_queries']}")
    print(f"  └ OLTP:            {stats['oltp_count']}")
    print(f"  └ Analyst:         {stats['analyst_count']}")
    print(f"  └ Admin:           {stats['admin_count']}")
    print(f"  └ Night jobs:      {stats['night_job_count']}")
    print(f"  Log file:          {stats['log_file']}")

    return stats


if __name__ == "__main__":
    stats = run_load_simulation(duration_hours=24)
    print(f"\nDone! Log file ready for ETL pipeline: {stats['log_file']}")
