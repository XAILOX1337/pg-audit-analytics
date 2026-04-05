"""
CSV log parser for PostgreSQL audit logs.

Parses pgAudit CSV log files into structured DataFrame
suitable for loading into the audit_data schema.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from etl.config import PG_LOG_PATH, RAW_LOGS_DIR, CSV_ENCODING


# pgAudit CSV log column positions (PostgreSQL csvlog format):
# 0: log_time
# 1: user_name
# 2: database_name
# 3: process_id
# 4: connection_from
# 5: session_id
# 6: session_line_num
# 7: command_tag
# 8: session_start_time
# 9: virtual_transaction_id
# 10: transaction_id
# 11: error_severity
# 12: error/query message
# 13: detail
# 14: hint
# 15: internal_query
# 16: internal_query_pos
# 17: context
# 18: location
# 19: application_name
# 20+ (pgAudit specific in message):
#     AUDIT: SESSION,<id>,<type>,<category>,<statement>,<parameter>,...

# Map operation types to categories
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
}


def parse_csv_log_line(line: str) -> Optional[Dict]:
    """Parse a single pgAudit CSV log line.

    Args:
        line: Raw CSV log line from PostgreSQL

    Returns:
        Dict with parsed fields or None if line is not an audit entry
    """
    line = line.strip()
    if not line:
        return None

    try:
        # Parse CSV fields (handle quoted fields with commas)
        fields = _csv_split(line)
        if len(fields) < 13:
            return None

        log_time = fields[0].strip('"')
        username = fields[1].strip('"')
        database = fields[2].strip('"')
        session_id = fields[5].strip('"')
        command_tag = fields[7].strip('"')
        message = fields[12].strip('"')
        application_name = fields[19].strip('"') if len(fields) > 19 else ""

        # Only process pgAudit entries
        if "AUDIT:" not in message:
            return None

        # Parse pgAudit message format:
        # AUDIT: SESSION,<id>,<type>,<category>,<statement>,<parameter>,<oid>,<relation>
        audit_parts = _parse_audit_message(message)
        if audit_parts is None:
            return None

        operation_type = audit_parts.get("type", "UNKNOWN").upper()
        operation_category = audit_parts.get("category", "OTHER").upper()
        raw_query = audit_parts.get("statement", "")
        table_name = audit_parts.get("relation", "")

        # Normalize category if missing
        if not operation_category or operation_category == "NONE":
            operation_category = OPERATION_CATEGORY_MAP.get(operation_type, "OTHER")

        # Extract duration if available (from separate log line or message)
        duration_ms = _extract_duration(message)

        # Generate simple query hash
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

    except (IndexError, ValueError):
        return None


def _csv_split(line: str) -> List[str]:
    """Split CSV line respecting quoted fields."""
    fields = []
    current = ""
    in_quotes = False

    for char in line:
        if char == '"':
            in_quotes = not in_quotes
            current += char
        elif char == ',' and not in_quotes:
            fields.append(current)
            current = ""
        else:
            current += char

    fields.append(current)
    return fields


def _parse_audit_message(message: str) -> Optional[Dict]:
    """Parse pgAudit AUDIT message into components.

    Format: AUDIT: SESSION,<id>,<type>,<category>,<statement>,<parameter>,<oid>,<relation>
    """
    if not message.startswith("AUDIT:"):
        return None

    # Remove "AUDIT: " prefix
    content = message[6:].strip()

    parts = _csv_split(content)
    if len(parts) < 5:
        return None

    result = {
        "session_type": parts[0].strip() if len(parts) > 0 else "",
        "id": parts[1].strip() if len(parts) > 1 else "",
        "type": parts[2].strip() if len(parts) > 2 else "UNKNOWN",
        "category": parts[3].strip() if len(parts) > 3 else "NONE",
        "statement": parts[4].strip() if len(parts) > 4 else "",
    }

    # Extract relation (table name) if present
    if len(parts) > 7 and parts[7].strip():
        result["relation"] = parts[7].strip()

    # Extract table name from statement if not in audit fields
    if not result.get("relation") and result["statement"]:
        result["relation"] = _extract_table_name(result["statement"])

    return result


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

    Args:
        file_path: Path to CSV log file
        max_lines: Maximum lines to parse (None = all)

    Returns:
        DataFrame with parsed audit log entries
    """
    records = []
    lines_processed = 0

    with open(file_path, "r", encoding=CSV_ENCODING, errors="replace") as f:
        for line in f:
            if max_lines and lines_processed >= max_lines:
                break

            record = parse_csv_log_line(line)
            if record:
                records.append(record)

            lines_processed += 1

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Convert timestamp to datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

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
