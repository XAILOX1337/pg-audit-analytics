import re
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, MinMaxScaler


# Regex patterns for query analysis
JOIN_PATTERN = re.compile(r'\bJOIN\b', re.IGNORECASE)
AGGREGATE_PATTERN = re.compile(r'\b(COUNT|SUM|AVG|MIN|MAX|GROUP\s+BY)\b', re.IGNORECASE)
WHERE_PATTERN = re.compile(r'\bWHERE\b', re.IGNORECASE)
SUBQUERY_PATTERN = re.compile(r'\bSELECT\b.*\bSELECT\b', re.IGNORECASE)
TABLE_PATTERN = re.compile(r'(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_.]*)', re.IGNORECASE)


def extract_time_features(df):
    """
    Extract temporal features from timestamp column.

    Creates features for time-based clustering:
    - hour_of_day: Activity patterns (work hours vs night)
    - day_of_week: Weekday vs weekend activity
    - is_night: Flag for suspicious off-hours activity (0-5 AM)
    - is_weekend: Weekend activity indicator
    - month, quarter: Seasonal patterns

    Args:
        df (pd.DataFrame): Input data with 'timestamp' column

    Returns:
        pd.DataFrame: DataFrame with added time feature columns
    """
    result = df.copy()
    ts = pd.to_datetime(result["timestamp"])

    result["hour_of_day"] = ts.dt.hour
    result["day_of_week"] = ts.dt.dayofweek  # 0=Monday, 6=Sunday
    result["is_night"] = (ts.dt.hour >= 0) & (ts.dt.hour <= 5)
    result["is_weekend"] = ts.dt.dayofweek >= 5
    result["month"] = ts.dt.month
    result["quarter"] = ts.dt.quarter

    return result


def extract_user_features(df):
    """
    Create per-user aggregated feature vectors.

    For each database user, compute:
    - total_queries: Activity volume
    - avg_duration_ms: Query performance profile
    - query_count_by_hour: 24-dim hourly activity pattern
    - read_ratio, write_ratio, ddl_ratio: Operation mix
    - unique_tables: Breadth of database access
    - night_query_ratio: Off-hours activity (security indicator)
    - avg_queries_per_day: Activity frequency

    Args:
        df (pd.DataFrame): Raw audit data with user activity

    Returns:
        pd.DataFrame: Feature matrix (users × features)
    """
    records = []

    for username, user_df in df.groupby("username"):
        features = {"username": username}

        # Volume and duration
        features["total_queries"] = len(user_df)
        features["avg_duration_ms"] = user_df["duration_ms"].mean() if "duration_ms" in user_df.columns else 0
        features["min_duration_ms"] = user_df["duration_ms"].min() if "duration_ms" in user_df.columns else 0
        features["max_duration_ms"] = user_df["duration_ms"].max() if "duration_ms" in user_df.columns else 0

        # Hourly activity distribution (24 dimensions)
        hour_counts = user_df["hour_of_day"].value_counts() if "hour_of_day" in user_df.columns else pd.Series()
        for h in range(24):
            features[f"hour_{h}"] = int(hour_counts.get(h, 0))

        # Operation type distribution
        op_counts = user_df["operation_category"].value_counts() if "operation_category" in user_df.columns else pd.Series()
        total_ops = op_counts.sum()
        if total_ops > 0:
            features["read_ratio"] = op_counts.get("READ", 0) / total_ops
            features["write_ratio"] = op_counts.get("WRITE", 0) / total_ops
            features["ddl_ratio"] = op_counts.get("DDL", 0) / total_ops
            features["dcl_ratio"] = op_counts.get("DCL", 0) / total_ops
        else:
            features["read_ratio"] = 0
            features["write_ratio"] = 0
            features["ddl_ratio"] = 0
            features["dcl_ratio"] = 0

        # Table access breadth
        if "table_name" in user_df.columns:
            features["unique_tables"] = user_df["table_name"].nunique()
        else:
            features["unique_tables"] = 0

        # Night activity
        if "is_night" in user_df.columns:
            features["night_query_ratio"] = user_df["is_night"].mean()
        else:
            features["night_query_ratio"] = 0

        # Weekend activity
        if "is_weekend" in user_df.columns:
            features["weekend_query_ratio"] = user_df["is_weekend"].mean()
        else:
            features["weekend_query_ratio"] = 0

        # Activity frequency (queries per day)
        if "timestamp" in df.columns and len(user_df) > 0:
            ts = pd.to_datetime(user_df["timestamp"])
            if len(ts) > 1:
                days_span = (ts.max() - ts.min()).total_seconds() / 86400
                days_span = max(days_span, 1)  # At least 1 day
                features["avg_queries_per_day"] = len(user_df) / days_span
            else:
                features["avg_queries_per_day"] = len(user_df)
        else:
            features["avg_queries_per_day"] = 0

        records.append(features)

    return pd.DataFrame(records)


def extract_query_patterns(df):
    """
    Analyze query text patterns for feature extraction.

    Extracts from SQL queries:
    - most_accessed_tables: Top 5 tables per user
    - join_count: Number of JOIN operations
    - has_aggregation: Uses COUNT/SUM/AVG/GROUP BY
    - has_where_clause: Selective vs full scans
    - query_length: Complexity proxy

    Args:
        df (pd.DataFrame): Data with 'raw_query' column

    Returns:
        pd.DataFrame: Query pattern feature columns
    """
    result = df.copy()

    # Join count per query
    result["join_count"] = result["raw_query"].apply(
        lambda q: len(JOIN_PATTERN.findall(q)) if isinstance(q, str) else 0
    )

    # Has aggregation
    result["has_aggregation"] = result["raw_query"].apply(
        lambda q: bool(AGGREGATE_PATTERN.search(q)) if isinstance(q, str) else False
    ).astype(int)

    # Has WHERE clause
    result["has_where_clause"] = result["raw_query"].apply(
        lambda q: bool(WHERE_PATTERN.search(q)) if isinstance(q, str) else False
    ).astype(int)

    # Has subquery
    result["has_subquery"] = result["raw_query"].apply(
        lambda q: bool(SUBQUERY_PATTERN.search(q)) if isinstance(q, str) else False
    ).astype(int)

    # Query length (character count)
    result["query_length"] = result["raw_query"].apply(
        lambda q: len(q) if isinstance(q, str) else 0
    )

    # Tables accessed in query
    result["tables_in_query"] = result["raw_query"].apply(
        lambda q: [t.split(".")[-1] for t in TABLE_PATTERN.findall(q)] if isinstance(q, str) else []
    )

    return result


def build_feature_matrix(df):
    """
    Build comprehensive feature matrix for ML algorithms.

    Combines:
    - Temporal features (time patterns)
    - User aggregation features (behavior profiles)
    - Query pattern features (access patterns)

    Handles:
    - Missing values (fill with 0 or median)
    - Feature naming for interpretability

    Args:
        df (pd.DataFrame): Raw audit log data

    Returns:
        tuple: (feature_matrix: pd.DataFrame, feature_names: list[str])
    """
    # Step 1: Extract time features
    df_time = extract_time_features(df)

    # Step 2: Extract query patterns
    df_patterns = extract_query_patterns(df_time)

    # Step 3: Aggregate per user
    feature_matrix = extract_user_features(df_patterns)

    # Step 4: Aggregate query patterns per user
    for username in feature_matrix["username"].values:
        user_queries = df_patterns[df_patterns["username"] == username]

        feature_matrix.loc[feature_matrix["username"] == username, "avg_join_count"] = user_queries["join_count"].mean()
        feature_matrix.loc[feature_matrix["username"] == username, "max_join_count"] = user_queries["join_count"].max()
        feature_matrix.loc[feature_matrix["username"] == username, "has_aggregation_ratio"] = user_queries["has_aggregation"].mean()
        feature_matrix.loc[feature_matrix["username"] == username, "has_where_clause_ratio"] = user_queries["has_where_clause"].mean()
        feature_matrix.loc[feature_matrix["username"] == username, "has_subquery_ratio"] = user_queries["has_subquery"].mean()
        feature_matrix.loc[feature_matrix["username"] == username, "avg_query_length"] = user_queries["query_length"].mean()

    # Step 5: Fill missing values
    feature_matrix = feature_matrix.fillna(0)

    # Ensure numeric columns
    numeric_cols = feature_matrix.select_dtypes(include=[np.number]).columns.tolist()
    feature_names = [c for c in numeric_cols if c != "username"]

    return feature_matrix, feature_names


def scale_features(feature_matrix, method="standard"):
    """
    Scale features for machine learning algorithms.

    Scaling methods:
    - "standard": StandardScaler (mean=0, std=1) — best for KMeans
    - "minmax": MinMaxScaler (range [0,1]) — best for DBSCAN

    Args:
        feature_matrix (pd.DataFrame or np.ndarray): Raw features
        method (str): "standard" or "minmax"

    Returns:
        tuple: (scaled_matrix: np.ndarray, fitted_scaler: sklearn scaler)
    """
    if method == "standard":
        scaler = StandardScaler()
    elif method == "minmax":
        scaler = MinMaxScaler()
    else:
        raise ValueError(f"Unknown scaling method: {method}. Use 'standard' or 'minmax'.")

    scaled = scaler.fit_transform(feature_matrix)
    return scaled, scaler


def prepare_for_clustering(df):
    """
    Prepare data for clustering analysis.

    Pipeline:
    1. Build feature matrix from raw data
    2. Scale features appropriately
    3. Return ready-to-use data for KMeans/DBSCAN

    Args:
        df (pd.DataFrame): Raw audit log data

    Returns:
        tuple: (
            X_scaled: np.ndarray (n_users, n_features),
            user_ids: list[str],
            feature_names: list[str],
            scaler: fitted sklearn scaler
        )
    """
    # Build feature matrix
    feature_matrix, feature_names = build_feature_matrix(df)

    # Extract user IDs
    user_ids = feature_matrix["username"].tolist()

    # Get numeric features only
    X = feature_matrix[feature_names].values

    # Scale features (standard for KMeans)
    X_scaled, scaler = scale_features(X, method="standard")

    return X_scaled, user_ids, feature_names, scaler


def prepare_for_anomaly_detection(df, window="1h"):
    """
    Prepare time series features for anomaly detection.

    Steps:
    1. Resample to specified time window
    2. Count transactions per window
    3. Calculate rolling statistics (mean, std, min, max)
    4. Add temporal features (hour, day_of_week)

    Args:
        df (pd.DataFrame): Audit log data with timestamps
        window (str): Time window for aggregation ("1h", "5min", etc.)

    Returns:
        pd.DataFrame: Time series with rolling features
    """
    ts_df = df.copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"])
    ts_df = ts_df.set_index("timestamp")

    # Aggregate per time window
    agg_dict = {
        "username": "nunique",
        "operation_type": "count",
    }

    if "duration_ms" in ts_df.columns:
        agg_dict["duration_ms"] = ["mean", "max"]

    ts_agg = ts_df.resample(window).agg(agg_dict)

    # Flatten column names
    ts_agg.columns = ["_".join(col).strip() for col in ts_agg.columns]
    ts_agg = ts_agg.rename(columns={
        "username_nunique": "unique_users",
        "operation_type_count": "transaction_count",
    })

    # Add operation type breakdowns
    if "operation_category" in ts_df.columns:
        for op_type in ts_df["operation_category"].unique():
            ts_agg[f"{op_type.lower()}_count"] = ts_df[ts_df["operation_category"] == op_type].resample(window).size()

    # Rolling statistics (window=6 for 6-hour rolling stats)
    if "transaction_count" in ts_agg.columns:
        ts_agg["rolling_mean_6h"] = ts_agg["transaction_count"].rolling(window=6, min_periods=1).mean()
        ts_agg["rolling_std_6h"] = ts_agg["transaction_count"].rolling(window=6, min_periods=1).std().fillna(0)
        ts_agg["rolling_max_6h"] = ts_agg["transaction_count"].rolling(window=6, min_periods=1).max()

    # Add temporal features
    ts_agg["hour_of_day"] = ts_agg.index.hour
    ts_agg["day_of_week"] = ts_agg.index.dayofweek
    ts_agg["is_night"] = (ts_agg.index.hour >= 0) & (ts_agg.index.hour <= 5)

    # Fill NaN
    ts_agg = ts_agg.fillna(0)

    return ts_agg


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))

    from etl.db_client import execute_query

    print("=== Feature Engineering Test ===")
    print("Loading data from audit_data.audit_logs...")

    try:
        df = execute_query("SELECT * FROM audit_data.audit_logs LIMIT 1000")
        if df.empty:
            print("No data found. Run ETL pipeline first.")
        else:
            print(f"Loaded {len(df)} records.")

            # Test feature extraction
            print("\n[1/3] Extracting time features...")
            df_time = extract_time_features(df)
            print(f"  Columns: {list(df_time.columns)}")

            print("\n[2/3] Building feature matrix...")
            feature_matrix, feature_names = build_feature_matrix(df)
            print(f"  Feature matrix shape: {feature_matrix.shape}")
            print(f"  Features: {feature_names}")

            print("\n[3/3] Scaling features...")
            X = feature_matrix[feature_names].values
            X_scaled, scaler = scale_features(X, method="standard")
            print(f"  Scaled matrix shape: {X_scaled.shape}")
            print(f"  Mean: {X_scaled.mean():.4f}, Std: {X_scaled.std():.4f}")

            print("\n=== Feature Engineering Complete ===")
    except Exception as e:
        print(f"Error: {e}")
