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
import random
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.db_client import get_connection, execute_query


# TODO: Define QUERY_TEMPLATES constant
# SQL query templates for different operation types
QUERY_TEMPLATES = {
    "SELECT": [
        "SELECT * FROM users WHERE id = {}",
        "SELECT name, email FROM customers WHERE region = '{}'",
        "SELECT COUNT(*) FROM orders WHERE date > '{}'",
        "SELECT p.name, o.total FROM products p JOIN orders o ON p.id = o.product_id",
    ],
    "INSERT": [
        "INSERT INTO logs (timestamp, message, level) VALUES ('{}', '{}', '{}')",
        "INSERT INTO audit_trail (user_id, action, timestamp) VALUES ({}, '{}', '{}')",
    ],
    "UPDATE": [
        "UPDATE users SET last_login = '{}' WHERE id = {}",
        "UPDATE orders SET status = '{}' WHERE id = {}",
    ],
    "DELETE": [
        "DELETE FROM temp_data WHERE created_at < '{}'",
        "DELETE FROM sessions WHERE expires_at < '{}'",
    ],
    "DDL": [
        "CREATE TABLE IF NOT EXISTS temp_table_{} (id INT, data TEXT)",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS processed BOOLEAN DEFAULT FALSE",
        "DROP TABLE IF EXISTS temp_table_{}",
    ]
}


# TODO: Define USER_PROFILES constant
# Different user types with their behavior patterns
USER_PROFILES = {
    "app_user": {
        "operations": {"SELECT": 0.6, "INSERT": 0.3, "UPDATE": 0.1},
        "tables": ["users", "orders", "products", "logs"],
        "frequency": "high",  # queries per minute
        "active_hours": range(8, 18),  # business hours
    },
    "analyst": {
        "operations": {"SELECT": 0.9, "INSERT": 0.1},
        "tables": ["orders", "customers", "products", "analytics"],
        "frequency": "medium",
        "active_hours": range(9, 17),
    },
    "admin": {
        "operations": {"SELECT": 0.3, "DDL": 0.5, "GRANT": 0.2},
        "tables": ["users", "logs", "audit_trail", "system_config"],
        "frequency": "low",
        "active_hours": range(10, 16),
    },
    "night_job": {
        "operations": {"SELECT": 0.7, "INSERT": 0.2, "DELETE": 0.1},
        "tables": ["orders", "logs", "temp_data", "analytics"],
        "frequency": "high",
        "active_hours": list(range(0, 6)) + [22, 23],  # night hours
    }
}


# TODO: Implement simulate_oltp_workload()
# Purpose: Generate OLTP transaction patterns (app_user)
# Characteristics:
#   - High frequency (10-50 queries per minute)
#   - Business hours only (8 AM - 6 PM)
#   - Mix of SELECT, INSERT, UPDATE
#   - Access to operational tables
# Input: number of minutes to simulate
# Returns: list of (timestamp, user, query) tuples
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
    pass


# TODO: Implement simulate_analyst_queries()
# Purpose: Generate analytical query patterns
# Characteristics:
#   - Medium frequency (5-15 queries per minute)
#   - Complex SELECT with JOINs and aggregations
#   - Business hours (9 AM - 5 PM)
#   - Long-running queries (analytics workloads)
# Input: number of minutes to simulate
# Returns: list of (timestamp, user, query, duration) tuples
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
    pass


# TODO: Implement simulate_admin_queries()
# Purpose: Generate administrator DDL operations
# Characteristics:
#   - Low frequency (1-3 operations per minute)
#   - DDL operations: CREATE, ALTER, DROP, GRANT
#   - Work hours (10 AM - 4 PM)
#   - Affects system tables and configurations
# Input: number of minutes to simulate
# Returns: list of (timestamp, user, query) tuples
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
    pass


# TODO: Implement simulate_night_jobs()
# Purpose: Generate night batch job patterns
# Characteristics:
#   - High frequency during night hours (0-5 AM)
#   - Heavy aggregations and batch processing
#   - Large data scans (full table scans)
#   - INSERT/DELETE heavy (ETL patterns)
# Input: number of minutes to simulate
# Returns: list of (timestamp, user, query) tuples
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
        list[tuple]: (timestamp, username, query) records
    """
    pass


# TODO: Implement simulate_suspicious_activity()
# Purpose: Generate anomalous patterns for testing detection
# Anomalies to inject:
#   1. Activity spike at 3 AM (sudden burst of queries)
#   2. User accessing unusual tables (admin accessing financial data)
#   3. Rapid DDL operations (potential schema attack)
#   4. Very long-running queries (resource abuse)
#   5. Unusual operation mix (read-only user doing DELETEs)
# Input: number of minutes to simulate
# Returns: list of (timestamp, user, query, anomaly_type) tuples
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
    pass


# TODO: Implement generate_csv_log()
# Purpose: Write simulated activity to PostgreSQL CSV log format
# Format: timestamp,username,database,pid,source,session_id,line,command_tag,...
# Input: list of (timestamp, user, query) tuples
# Output: CSV file in data/raw_logs/
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
    pass


# TODO: Implement run_load_simulation()
# Purpose: Main orchestrator for load generation
# Steps:
#   1. Simulate all user types (OLTP, analyst, admin, night jobs)
#   2. Inject suspicious activity (10% of total)
#   3. Combine all records
#   4. Generate CSV log file
#   5. Optionally load directly to database
#   6. Print summary statistics
# Returns: dict with simulation stats
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
    pass


if __name__ == "__main__":
    # TODO: When run directly, execute 24-hour load simulation
    # Generate CSV logs for ETL pipeline testing
    stats = run_load_simulation(duration_hours=24)
    print(f"Simulation complete: {stats}")
