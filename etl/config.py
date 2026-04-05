"""
Configuration module for database connections and file paths.

Centralizes all configuration parameters to avoid
hardcoding values across the project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# TODO: Fill in database configuration from environment variables
# Read: PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
# Provide defaults for local development
# Example: DB_CONFIG = {"host": os.getenv("PG_HOST", "localhost"), ...}
DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
    "database": os.getenv("PG_DATABASE", "postgres"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
}


# TODO: Define file path constants
# Use Path objects for cross-platform compatibility
# Paths relative to project root
PROJECT_ROOT = Path(__file__).parent.parent

RAW_LOGS_DIR = PROJECT_ROOT / "data" / "raw_logs"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# Schema and table names
AUDIT_SCHEMA = "audit_data"
AUDIT_TABLES = {
    "audit_logs": "audit_data.audit_logs",
    "user_activity": "audit_data.user_activity",
    "query_stats": "audit_data.query_stats",
}

# TODO: Define log format constants
# PostgreSQL CSV log encoding
LOG_ENCODING = "utf-8"

# Batch size for bulk inserts
BATCH_SIZE = 1000

# Maximum query length to store (truncate longer queries)
MAX_QUERY_LENGTH = 10000

# Valid operation types
VALID_OPERATIONS = {"SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "GRANT", "REVOKE", "TRUNCATE"}

# Operation category mapping
OPERATION_CATEGORIES = {
    "SELECT": "READ",
    "INSERT": "WRITE",
    "UPDATE": "WRITE",
    "DELETE": "WRITE",
    "CREATE": "DDL",
    "ALTER": "DDL",
    "DROP": "DDL",
    "TRUNCATE": "DDL",
    "GRANT": "DCL",
    "REVOKE": "DCL",
}


def get_database_url():
    """
    Construct SQLAlchemy database URL from DB_CONFIG.
    
    Returns:
        str: Database URL in format postgresql://user:password@host:port/database
    """
    # TODO: Implement URL construction
    # Format: postgresql://{user}:{password}@{host}:{port}/{database}
    pass


def ensure_directories():
    """
    Create data directories if they don't exist.
    
    Ensures raw_logs/ and processed/ directories exist.
    """
    # TODO: Implement directory creation
    # Use Path.mkdir(parents=True, exist_ok=True)
    pass


if __name__ == "__main__":
    # TODO: When run directly, print current configuration
    # Useful for debugging: print(f"DB Config: {DB_CONFIG}")
    pass
