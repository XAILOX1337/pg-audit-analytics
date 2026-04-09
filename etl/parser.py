"""
CSV log parser for PostgreSQL audit logs.

Parses standard PostgreSQL CSV log files (log_destination = 'csvlog')
into structured DataFrame suitable for loading into the audit_data schema.

Works WITHOUT pgAudit — uses standard PostgreSQL statement logging.
"""

import re
import csv
import hashlib
import io
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from config import PG_LOG_PATH, RAW_LOGS_DIR, CSV_ENCODING


# PostgreSQL CSV log column positions (standard csvlog format, 22 columns):
#  0: log_time
#  1: user_name
#  2: database_name
#  3: process_id
#  4: connection_from
#  5: session_id
#  6: session_line_num
#  7: command_tag          ← SELECT, INSERT, UPDATE, DELETE, CREATE, etc.
#  8: session_start_time
#  9: virtual_transaction_id
# 10: transaction_id
# 11: error_severity       ← LOG, FATAL, ERROR, etc.
# 12: sql_state_code       ← 00000, etc.
# 13: message              ← the actual SQL statement when log_statement='all'
# 14: detail
# 15: hint
# 16: internal_query
# 17: internal_query_pos
# 18: context
# 19: location
# 20: application_name
# 21: backend_type
# 22: leader_pid

# Map command_tag (operation type) to category
OPERATION_CATEGORY_MAP = {
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
    "DISCARD": "DCL",
    "COPY": "WRITE",
}

# Command tags that represent log entries we want to capture
VALID_COMMAND_TAGS = {
    "SELECT", "INSERT", "UPDATE", "DELETE",
    "CREATE", "ALTER", "DROP", "TRUNCATE",
    "GRANT", "REVOKE", "COPY",
}


def _extract_command_tag_from_statement(message: str) -> Optional[str]:
    """Extract command type from SQL statement when command_tag is empty.

    This handles cases where log_statement='all' is set but command_tag
    field is empty in the CSV log.
    """
    if not message:
        return None

    # Remove 'statement: ' prefix if present
    stmt = message
    if stmt.lower().startswith("statement: "):
        stmt = stmt[11:]

    stmt_upper = stmt.strip().upper()

    # Check for common SQL commands at the start of the statement
    commands = [
        "SELECT", "INSERT", "UPDATE", "DELETE",
        "CREATE", "ALTER", "DROP", "TRUNCATE",
        "GRANT", "REVOKE", "COPY", "DISCARD",
    ]

    for cmd in commands:
        if stmt_upper.startswith(cmd):
            return cmd

    return None


def parse_csv_log_line(line: str) -> Optional[Dict]:
    """Parse a single standard PostgreSQL CSV log line.

    Works with log_destination = 'csvlog' and log_statement = 'all'.

    Args:
        line: Raw CSV log line from PostgreSQL

    Returns:
        Dict with parsed fields or None if line is not relevant
    """
    line = line.strip()
    if not line:
        return None

    try:
        
        reader = csv.reader(io.StringIO(line))
        fields = next(reader)
        
        if len(fields) < 14:
            return None

        log_time = fields[0]
        username = fields[1]
        database = fields[2]
        session_id = fields[5]
        command_tag = fields[7]
        severity = fields[11]
        message = fields[13]  # message is at index 13
        application_name = fields[20] if len(fields) > 20 else ""

        # If command_tag is empty, try to extract it from the SQL statement
        if not command_tag:
            command_tag = _extract_command_tag_from_statement(message)

        # Filter: only process rows with valid command tags
        if command_tag not in VALID_COMMAND_TAGS:
            return None

        
        if not username or username == "":
            return None

        # The SQL statement is in field 13 (message) when log_statement = 'all'
        # Extract actual SQL from 'statement:' prefix if present
        raw_query = _extract_statement(message)

        # Determine operation type from command_tag
        operation_type = command_tag.upper()
        operation_category = OPERATION_CATEGORY_MAP.get(operation_type, "OTHER")

        # Extract table name from the SQL statement
        table_name = _extract_table_name(raw_query) if raw_query else ""

        # Extract duration if present (appears as: duration: 12.345 ms)
        duration_ms = _extract_duration(message)

        # Compute query hash for deduplication
        query_hash = _compute_query_hash(raw_query) if raw_query else None

        return {
            "timestamp": log_time,
            "username": username,
            "database_name": database,
            "operation_type": operation_type,
            "operation_category": operation_category,
            "table_name": table_name if table_name else None,
            "duration_ms": duration_ms,
            "raw_query": raw_query if raw_query else None,
            "query_hash": query_hash,
            "session_id": session_id,
            "application_name": application_name,
        }

    except (IndexError, ValueError, StopIteration):
        return None


def _extract_statement(message: str) -> str:
    """Extract the actual SQL statement from the log message.

    In standard PostgreSQL logs with log_statement='all', the message
    field contains the raw SQL. It may have a 'statement: ' prefix.

    Args:
        message: Log message field from CSV

    Returns:
        The SQL statement string
    """
    if not message:
        return ""

    # Remove 'statement: ' prefix if present
    if message.lower().startswith("statement: "):
        return message[11:].strip()

    return message.strip()


def _csv_split(line: str) -> List[str]:
    """Split CSV line respecting quoted fields.
    
    Deprecated: Use Python's csv module instead for proper handling.
    """
    import io
    reader = csv.reader(io.StringIO(line))
    return next(reader)


def _extract_table_name(query: str) -> str:
    """Extract table name from SQL statement (simplified)."""
    query_upper = query.upper().strip()

    patterns = [
        (r'(?:FROM|INTO|UPDATE|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_.]*)', 1),
        (r'(?:CREATE|ALTER|DROP|TRUNCATE)\s+(?:TABLE\s+)?([a-zA-Z_][a-zA-Z0-9_.]*)', 1),
        (r'INSERT\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_.]*)', 1),
    ]

    for pattern, group in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            table = match.group(group)
            # Remove schema prefix if present
            if '.' in table:
                table = table.split('.')[-1]
            return table

    return ""


def _extract_duration(message: str) -> Optional[float]:
    """Extract query duration from log message (if present).

    Duration appears in separate log line: duration: 12.345 ms
    """
    match = re.search(r'duration:\s*([\d.]+)\s*ms', message)
    if match:
        return float(match.group(1))
    return None


def _compute_query_hash(query: str) -> str:
    """Compute simplified query hash (normalize literals, then hash)."""
    import hashlib

    normalized = query.lower().strip()
    # Replace string literals
    normalized = re.sub(r"'[^']*'", "?", normalized)
    # Replace numbers
    normalized = re.sub(r'\b\d+\b', "?", normalized)
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized)

    return hashlib.sha256(normalized.encode()).hexdigest()


def parse_log_file(file_path: str, max_lines: Optional[int] = None) -> pd.DataFrame:
    """Parse an entire pgAudit CSV log file.

    Handles multiline CSV log entries (SQL statements that span multiple lines).

    Args:
        file_path: Path to CSV log file
        max_lines: Maximum lines to parse (None = all)

    Returns:
        DataFrame with parsed audit log entries
    """
    records = []
    lines_processed = 0
    current_record_lines = []
    in_multiline_record = False

    with open(file_path, "r", encoding=CSV_ENCODING, errors="replace") as f:
        for line in f:
            if max_lines and lines_processed >= max_lines:
                break

            line = line.rstrip('\n').rstrip('\r')
            
            # Check if this line starts a new CSV record
            # A new record starts with a timestamp pattern: YYYY-MM-DD HH:MM:SS
            if re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', line):
                # If we have accumulated lines from a previous multiline record, process them
                if current_record_lines:
                    full_line = '\n'.join(current_record_lines)
                    record = parse_csv_log_line(full_line)
                    if record:
                        records.append(record)
                    current_record_lines = []
                    in_multiline_record = False
                
                # Start new record
                current_record_lines.append(line)
                in_multiline_record = True
            elif in_multiline_record:
                # This is a continuation of the previous record
                current_record_lines.append(line)

            lines_processed += 1

    # Process the last accumulated multiline record
    if current_record_lines:
        full_line = '\n'.join(current_record_lines)
        record = parse_csv_log_line(full_line)
        if record:
            records.append(record)

    df = pd.DataFrame(records)
    if df.empty:
        return df
    # Convert timestamp to datetime
    # Remove timezone abbreviation (MSK, etc.)
    df["timestamp"] = df["timestamp"].astype(str).str.replace(r'\s+[A-Z]{2,4}$', '', regex=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format='%Y-%m-%d %H:%M:%S.%f', errors="coerce")

    # Drop rows with invalid timestamps
    df = df.dropna(subset=["timestamp"])

    return df


def find_csv_log_files(log_path: Optional[str] = None) -> List[Path]:
    """Find all pgAudit CSV log files in the log directory.

    Args:
        log_path: Path to log directory (defaults to PG_LOG_PATH)

    Returns:
        List of CSV file paths sorted by modification time
    """
    print(PG_LOG_PATH)
    path = Path(log_path or PG_LOG_PATH)
    if not path.exists():
        print(f"Log directory not found: {path}")
        return []

    csv_files = sorted(
        path.glob("*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return csv_files


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate parsed audit data.

    - Remove duplicates
    - Fill missing values
    - Validate operation types
    - Standardize categories

    Args:
        df: Raw parsed DataFrame

    Returns:
        Cleaned DataFrame
    """
    if df.empty:
        return df

    # Drop exact duplicates
    df = df.drop_duplicates()

    # Standardize operation types
    df["operation_type"] = df["operation_type"].str.upper()
    df["operation_category"] = df["operation_category"].str.upper()

    # Fix categories based on operation type
    for op, cat in OPERATION_CATEGORY_MAP.items():
        mask = df["operation_type"] == op
        df.loc[mask, "operation_category"] = cat

    # Ensure duration is numeric
    df["duration_ms"] = pd.to_numeric(df["duration_ms"], errors="coerce")

    # Fill N/A values
    df["table_name"] = df["table_name"].fillna("")
    df["raw_query"] = df["raw_query"].fillna("")

    return df


def validate_record(record: Dict) -> bool:
    """Validate a single parsed record.

    Args:
        record: Dict from parse_csv_log_line()

    Returns:
        True if record is valid
    """
    required_fields = ["timestamp", "username", "operation_type"]
    for field in required_fields:
        if not record.get(field):
            return False

    valid_ops = {
        "SELECT", "INSERT", "UPDATE", "DELETE",
        "CREATE", "ALTER", "DROP", "TRUNCATE",
        "GRANT", "REVOKE",
    }
    if record["operation_type"] not in valid_ops:
        return False

    return True


def run_parser(log_path: Optional[str] = None, max_files: int = 5) -> pd.DataFrame:
    """Main parser entry point: find and parse log files.

    Args:
        log_path: Override log directory path
        max_files: Maximum number of log files to parse

    Returns:
        Combined DataFrame from all parsed files
    """
    csv_files = find_csv_log_files(log_path)
    if not csv_files:
        print("No CSV log files found.")
        return pd.DataFrame()

    csv_files = csv_files[:max_files]
    print(f"Parsing {len(csv_files)} log file(s)...")

    all_records = []
    for csv_file in csv_files:
        print(f"  Processing: {csv_file.name}")
        df = parse_log_file(str(csv_file))
        if not df.empty:
            all_records.append(df)

    if not all_records:
        print("No audit records found in log files.")
        return pd.DataFrame()

    combined = pd.concat(all_records, ignore_index=True)
    combined = clean_data(combined)

    print(f"Parsed {len(combined)} audit records.")
    return combined


if __name__ == "__main__":
    print("=== pg-audit-analytics: CSV Log Parser ===")
    df = run_parser()
    if not df.empty:
        print(f"\nColumns: {list(df.columns)}")
        print(f"\nFirst 5 records:")
        print(df.head())
        print(f"\nOperation distribution:")
        print(df["operation_type"].value_counts())
