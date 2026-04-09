"""
Database client utilities.

Provides connection management, query execution,
and bulk data loading for PostgreSQL via SQLAlchemy.
"""

from contextlib import contextmanager
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import DB_CONFIG, get_connection_string, ensure_directories

# Global engine singleton
_engine: Optional[Engine] = None


def get_engine() -> Engine:
    """Get or create SQLAlchemy engine (singleton)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_connection_string(),
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def reset_engine():
    """Reset engine (useful after config changes)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def get_connection():
    """Context manager for database connections.

    Usage:
        with get_connection() as conn:
            result = conn.execute(text("SELECT 1"))
    """
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


def execute_query(query: str, params: Optional[Dict] = None) -> pd.DataFrame:
    """Execute a SELECT query and return results as DataFrame.

    Args:
        query: SQL query string
        params: Optional query parameters

    Returns:
        DataFrame with query results
    """
    with get_connection() as conn:
        return pd.read_sql(text(query), conn, params=params or {})


def execute_statement(query: str, params: Optional[Dict] = None) -> None:
    """Execute a DDL/DML statement (no return value).

    Args:
        query: SQL statement string
        params: Optional statement parameters
    """
    with get_connection() as conn:
        conn.execute(text(query), params or {})


def bulk_insert(df: pd.DataFrame, table_name: str, if_exists: str = "append") -> int:
    """Insert DataFrame into PostgreSQL table.

    Args:
        df: Data to insert
        table_name: Target table name (in audit_data schema)
        if_exists: 'append', 'replace', or 'fail'

    Returns:
        Number of rows inserted
    """
    engine = get_engine()
    full_table = f"audit_data.{table_name}"
    rows_inserted = len(df)

    df.to_sql(
        name=table_name,
        con=engine,
        schema="audit_data",
        if_exists=if_exists,
        index=False,
        method="multi",
        chunksize=1000,
    )

    return rows_inserted


def init_audit_schema(sql_file_path: Optional[str] = None) -> None:
    """Initialize audit_data schema by running SQL script.

    Args:
        sql_file_path: Path to SQL initialization script.
                       Defaults to sql/init_schema.sql in project root.
    """
    from etl.config import PROJECT_ROOT

    if sql_file_path is None:
        sql_file_path = str(PROJECT_ROOT / "sql" / "init_schema.sql")

    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    execute_statement(sql_script)
    print(f"Audit schema initialized from: {sql_file_path}")


def get_table_count(table_name: str) -> int:
    """Get row count for a table in audit_data schema.

    Args:
        table_name: Table name (without schema prefix)

    Returns:
        Number of rows in the table
    """
    query = f"SELECT COUNT(*) as cnt FROM audit_data.{table_name}"
    result = execute_query(query)
    return int(result.iloc[0]["cnt"])


def list_audit_tables() -> List[str]:
    """List all tables in audit_data schema.

    Returns:
        List of table names
    """
    query = """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'audit_data'
        ORDER BY tablename
    """
    result = execute_query(query)
    return result["tablename"].tolist()


def run_sql_file(sql_file_path: str) -> None:
    """Run a SQL file against the database.

    Args:
        sql_file_path: Absolute path to .sql file
    """
    with open(sql_file_path, "r", encoding="utf-8") as f:
        sql_script = f.read()

    execute_statement(sql_script)
    print(f"Executed SQL file: {sql_file_path}")


if __name__ == "__main__":
    ensure_directories()
    print("Testing database connection...")
    try:
        tables = list_audit_tables()
        print(f"Found {len(tables)} tables in audit_data schema:")
        for t in tables:
            count = get_table_count(t)
            print(f"  - {t}: {count} rows")
    except Exception as e:
        print(f"Connection failed: {e}")
        print("Make sure PostgreSQL is running and .env is configured.")
