"""
Database connection configuration.

Loads PostgreSQL connection parameters from .env file
and provides them to other modules.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Database connection parameters
DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "database": os.getenv("PG_DATABASE", "postgres"),
}

# Log path for reading PostgreSQL CSV logs
PG_LOG_PATH = os.getenv(
    "PG_LOG_PATH",
    r"C:\Program Files\PostgreSQL\16\data\log"
)

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_LOGS_DIR = PROJECT_ROOT / "data" / "raw_logs"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# ETL settings
BATCH_SIZE = 1000
CSV_ENCODING = "utf-8-sig"  # Handles BOM in CSV files


def get_connection_string():
    """Build PostgreSQL connection string for SQLAlchemy."""
    return (
        f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )


def get_psql_command():
    """Build psql command prefix for running SQL scripts."""
    pg_user = DB_CONFIG["user"]
    pg_host = DB_CONFIG["host"]
    pg_port = DB_CONFIG["port"]
    pg_database = DB_CONFIG["database"]
    return f"psql -U {pg_user} -h {pg_host} -p {pg_port} -d {pg_database}"


def ensure_directories():
    """Create data directories if they don't exist."""
    RAW_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print("=== pg-audit-analytics Configuration ===")
    print(f"Host: {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print(f"User: {DB_CONFIG['user']}")
    print(f"Database: {DB_CONFIG['database']}")
    print(f"Log path: {PG_LOG_PATH}")
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Raw logs dir: {RAW_LOGS_DIR}")
    print(f"Processed dir: {PROCESSED_DIR}")
