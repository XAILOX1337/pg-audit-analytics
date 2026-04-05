"""
Data loader for audit analytics.

Loads parsed audit log data into the audit_data schema
and provides aggregation utilities.
"""

import pandas as pd
from typing import Optional

from etl.config import RAW_LOGS_DIR, PROCESSED_DIR, BATCH_SIZE
from etl.db_client import (
    bulk_insert,
    execute_query,
    execute_statement,
    get_table_count,
)
from etl.parser import run_parser, clean_data


def load_audit_logs(df: pd.DataFrame, if_exists: str = "append") -> int:
    """Load parsed audit logs into audit_data.audit_logs table.

    Args:
        df: DataFrame with parsed audit records
        if_exists: 'append', 'replace', or 'fail'

    Returns:
        Number of rows loaded
    """
    if df.empty:
        print("No data to load.")
        return 0

    # Select only columns that exist in audit_logs table
    columns = [
        "timestamp", "username", "database_name", "operation_type",
        "operation_category", "table_name", "duration_ms", "raw_query",
        "query_hash", "session_id", "application_name",
    ]
    available_cols = [c for c in columns if c in df.columns]
    load_df = df[available_cols].copy()

    # Ensure timestamp is string for SQLAlchemy
    load_df["timestamp"] = pd.to_datetime(load_df["timestamp"])

    rows = bulk_insert(load_df, "audit_logs", if_exists=if_exists)
    print(f"Loaded {rows} records into audit_data.audit_logs")
    return rows


def aggregate_user_activity() -> int:
    """Compute and store user activity aggregations.

    Reads from audit_data.audit_logs and writes to
    audit_data.user_activity.

    Returns:
        Number of aggregation rows created
    """
    query = """
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
            updated_at = NOW()
    """
    execute_statement(query)
    count = get_table_count("user_activity")
    print(f"User activity aggregation complete: {count} rows")
    return count


def compute_query_stats() -> int:
    """Compute and store query performance statistics.

    Reads from audit_data.audit_logs and writes to
    audit_data.query_stats.

    Returns:
        Number of query pattern rows created
    """
    query = """
        INSERT INTO audit_data.query_stats (
            query_pattern, query_hash, operation_type, table_name,
            execution_count, avg_duration_ms, min_duration_ms,
            max_duration_ms, p50_duration_ms, p95_duration_ms,
            p99_duration_ms, first_seen, last_seen
        )
        SELECT
            raw_query AS query_pattern,
            query_hash,
            operation_type,
            table_name,
            COUNT(*) AS execution_count,
            ROUND(AVG(duration_ms), 3) AS avg_duration_ms,
            ROUND(MIN(duration_ms), 3) AS min_duration_ms,
            ROUND(MAX(duration_ms), 3) AS max_duration_ms,
            ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms), 3) AS p50_duration_ms,
            ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms), 3) AS p95_duration_ms,
            ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms), 3) AS p99_duration_ms,
            MIN(timestamp) AS first_seen,
            MAX(timestamp) AS last_seen
        FROM audit_data.audit_logs
        WHERE duration_ms IS NOT NULL AND query_hash IS NOT NULL
        GROUP BY raw_query, query_hash, operation_type, table_name
        ON CONFLICT (query_hash)
        DO UPDATE SET
            execution_count = EXCLUDED.execution_count,
            avg_duration_ms = EXCLUDED.avg_duration_ms,
            min_duration_ms = EXCLUDED.min_duration_ms,
            max_duration_ms = EXCLUDED.max_duration_ms,
            p50_duration_ms = EXCLUDED.p50_duration_ms,
            p95_duration_ms = EXCLUDED.p95_duration_ms,
            p99_duration_ms = EXCLUDED.p99_duration_ms,
            last_seen = EXCLUDED.last_seen
    """
    execute_statement(query)
    count = get_table_count("query_stats")
    print(f"Query stats computation complete: {count} rows")
    return count


def create_indexes() -> None:
    """Create performance indexes on audit tables."""
    indexes = [
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_timestamp ON audit_data.audit_logs (timestamp)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_username ON audit_data.audit_logs (username)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_operation_type ON audit_data.audit_logs (operation_type)",
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_table_name ON audit_data.audit_logs (table_name)",
    ]
    for idx in indexes:
        try:
            execute_statement(idx)
        except Exception as e:
            print(f"  Index warning: {e}")
    print("Indexes created/verified.")


def run_etl_pipeline(
    log_path: Optional[str] = None,
    max_files: int = 5,
    replace: bool = False,
) -> dict:
    """Run the complete ETL pipeline.

    Steps:
    1. Parse CSV log files from PostgreSQL
    2. Clean and validate data
    3. Load into audit_data.audit_logs
    4. Compute aggregations (user_activity, query_stats)
    5. Create indexes

    Args:
        log_path: Override log directory path
        max_files: Maximum number of log files to parse
        replace: If True, replace existing data; otherwise append

    Returns:
        Dict with pipeline statistics
    """
    print("=" * 60)
    print("Starting ETL Pipeline")
    print("=" * 60)

    # Step 1: Parse logs
    print("\n[1/4] Parsing CSV log files...")
    df = run_parser(log_path, max_files)
    if df.empty:
        print("No data parsed. Aborting ETL.")
        return {"parsed": 0, "loaded": 0, "aggregations": {}}

    # Step 2: Clean data
    print("\n[2/4] Cleaning data...")
    df = clean_data(df)
    parsed_count = len(df)
    print(f"  Clean records: {parsed_count}")

    # Step 3: Load to database
    print("\n[3/4] Loading to database...")
    if_exists_mode = "replace" if replace else "append"
    loaded_count = load_audit_logs(df, if_exists=if_exists_mode)

    # Step 4: Compute aggregations
    print("\n[4/4] Computing aggregations...")
    user_activity_count = aggregate_user_activity()
    query_stats_count = compute_query_stats()

    print("\n" + "=" * 60)
    print("ETL Pipeline Complete")
    print("=" * 60)
    print(f"  Records parsed:  {parsed_count}")
    print(f"  Records loaded:  {loaded_count}")
    print(f"  User activity:   {user_activity_count} rows")
    print(f"  Query stats:     {query_stats_count} rows")

    return {
        "parsed": parsed_count,
        "loaded": loaded_count,
        "aggregations": {
            "user_activity": user_activity_count,
            "query_stats": query_stats_count,
        },
    }


if __name__ == "__main__":
    result = run_etl_pipeline()
    print(f"\nETL Result: {result}")
