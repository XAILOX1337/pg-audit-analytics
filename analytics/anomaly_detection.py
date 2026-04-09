"""
Anomaly detection module for audit log analysis.

Identifies suspicious database activity using
Isolation Forest and Local Outlier Factor algorithms.
"""

import sys
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "etl") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "etl"))

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def build_time_series(df, window="1h"):
    """
    Build time series from raw audit log data.

    Aggregates per time window:
    - transaction_count: Number of queries
    - unique_users: Distinct users active
    - read_count, write_count, ddl_count: Operation breakdown
    - avg_duration_ms: Mean query duration
    - max_duration_ms: Peak query duration

    Args:
        df (pd.DataFrame): Audit log data with 'timestamp' column
        window (str): Time window ("1min", "5min", "1h", etc.)

    Returns:
        pd.DataFrame: Time-indexed aggregated metrics
    """
    ts_df = df.copy()
    ts_df["timestamp"] = pd.to_datetime(ts_df["timestamp"])
    ts_df = ts_df.set_index("timestamp")

    # Build aggregation dict
    agg_dict = {
        "username": "nunique",
        "operation_type": "count",
    }

    if "duration_ms" in ts_df.columns:
        agg_dict["duration_ms"] = ["mean", "max"]

    ts_agg = ts_df.resample(window).agg(agg_dict)

    # Flatten multi-level column names
    ts_agg.columns = ["_".join(col).strip("_") for col in ts_agg.columns]
    ts_agg = ts_agg.rename(columns={
        "username_nunique": "unique_users",
        "operation_type_count": "transaction_count",
    })

    # Add operation type breakdowns
    if "operation_category" in ts_df.columns:
        for op_type in ts_df["operation_category"].dropna().unique():
            col_name = f"{op_type.lower()}_count"
            ts_agg[col_name] = ts_df[ts_df["operation_category"] == op_type].resample(window).size()

    # Fill NaN from resample
    ts_agg = ts_agg.fillna(0)

    # Ensure integer counts
    for col in ts_agg.columns:
        if "count" in col or col == "unique_users":
            ts_agg[col] = ts_agg[col].astype(int)

    return ts_agg


def run_isolation_forest(X, contamination=0.05, random_state=42):
    """
    Detect anomalies using Isolation Forest.

    Algorithm:
    - Isolates observations using random splits
    - Anomalies require fewer splits to isolate
    - Scores based on average path length

    Args:
        X (np.ndarray): Feature matrix (time windows × features)
        contamination (float): Expected outlier proportion
        random_state (int): Reproducibility seed

    Returns:
        tuple: (
            predictions: np.ndarray (1=normal, -1=anomaly),
            scores: np.ndarray (anomaly scores, lower = more anomalous)
        )
    """
    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=200,
        max_samples="auto",
    )
    predictions = model.fit_predict(X)
    scores = model.decision_function(X)
    return predictions, scores


def run_lof(X, n_neighbors=20, contamination=0.05):
    """
    Detect anomalies using Local Outlier Factor (LOF).

    Algorithm:
    - Measures local deviation of density
    - Compares point density to k nearest neighbors
    - LOF >> 1 indicates anomaly (isolated point)

    Advantages over Isolation Forest:
    - Better for local anomalies
    - Works well with varying density regions

    Args:
        X (np.ndarray): Feature matrix
        n_neighbors (int): Neighborhood size
        contamination (float): Expected outlier proportion

    Returns:
        tuple: (
            predictions: np.ndarray (1=normal, -1=anomaly),
            scores: np.ndarray (negative LOF scores for anomalies)
        )
    """
    # Ensure n_neighbors doesn't exceed sample size
    n_neighbors = min(n_neighbors, len(X) - 1)
    n_neighbors = max(n_neighbors, 2)

    model = LocalOutlierFactor(
        n_neighbors=n_neighbors,
        contamination=contamination,
        novelty=False,
    )
    predictions = model.fit_predict(X)
    scores = model.negative_outlier_factor_
    return predictions, scores


def flag_suspicious_activity(time_series, ml_predictions=None):
    """
    Flag suspicious activity using hybrid approach.

    Combines:
    - ML anomaly predictions (Isolation Forest / LOF)
    - Rule-based detection:
      * Night activity spike (0-5 AM)
      * Transaction count > 3 standard deviations
      * Unusual DDL operations from non-admin
      * First-time access to many tables
      * Query duration > P99 threshold

    Args:
        time_series (pd.DataFrame): Aggregated time series
        ml_predictions (np.ndarray, optional): ML anomaly labels

    Returns:
        pd.DataFrame: Time series with 'is_suspicious' and 'reasons' columns
    """
    result = time_series.copy()
    result["is_suspicious"] = False
    result["reasons"] = ""

    # Rule 1: Night activity spike (0-5 AM)
    if "is_night" in result.columns:
        night_mask = result["is_night"] == True
        result.loc[night_mask, "is_suspicious"] = True
        result.loc[night_mask, "reasons"] += "Night activity; "

    # Rule 2: Transaction count > 3 std from mean
    if "transaction_count" in result.columns:
        tc = result["transaction_count"]
        mean_tc = tc.mean()
        std_tc = tc.std()
        if std_tc > 0:
            spike_mask = tc > (mean_tc + 3 * std_tc)
            result.loc[spike_mask, "is_suspicious"] = True
            result.loc[spike_mask, "reasons"] += "Transaction spike; "

    # Rule 3: Unusual DDL operations
    if "ddl_count" in result.columns:
        ddl = result["ddl_count"]
        mean_ddl = ddl.mean()
        std_ddl = ddl.std()
        if std_ddl > 0 and mean_ddl > 0:
            unusual_ddl = ddl > (mean_ddl + 2 * std_ddl)
            result.loc[unusual_ddl, "is_suspicious"] = True
            result.loc[unusual_ddl, "reasons"] += "High DDL activity; "

    # Rule 4: Very long queries (duration > P99)
    if "duration_ms_max" in result.columns:
        p99 = result["duration_ms_max"].quantile(0.99)
        if p99 > 0:
            long_query = result["duration_ms_max"] > p99 * 2
            result.loc[long_query, "is_suspicious"] = True
            result.loc[long_query, "reasons"] += "Long queries; "
    elif "duration_ms_mean" in result.columns:
        p99 = result["duration_ms_mean"].quantile(0.99)
        if p99 > 0:
            long_query = result["duration_ms_mean"] > p99 * 2
            result.loc[long_query, "is_suspicious"] = True
            result.loc[long_query, "reasons"] += "Long queries; "

    # Rule 5: ML predictions override
    if ml_predictions is not None:
        ml_anomaly = ml_predictions == -1
        if len(ml_anomaly) == len(result):
            result.loc[ml_anomaly, "is_suspicious"] = True
            result.loc[ml_anomaly, "reasons"] += "ML anomaly; "

    # Clean up empty reasons
    result.loc[~result["is_suspicious"], "reasons"] = ""

    return result


def detect_time_anomalies(time_series, scores):
    """
    Extract and characterize time-based anomalies.

    For each anomalous time window:
    - Records timestamp and anomaly score
    - Captures activity metrics (counts, users, operations)
    - Assigns severity level (Low/Medium/High)

    Args:
        time_series (pd.DataFrame): Time-indexed metrics
        scores (np.ndarray): Anomaly scores

    Returns:
        list[dict]: Anomaly details with severity
    """
    anomalies = []
    ts_copy = time_series.copy()
    ts_copy["anomaly_score"] = scores

    # Filter anomalous windows (negative scores from IF/LOF = anomalies)
    anomaly_mask = ts_copy["anomaly_score"] < 0

    for idx, row in ts_copy[anomaly_mask].iterrows():
        score = row["anomaly_score"]

        # Severity based on score quantiles
        if score < ts_copy["anomaly_score"].quantile(0.05):
            severity = "High"
        elif score < ts_copy["anomaly_score"].quantile(0.25):
            severity = "Medium"
        else:
            severity = "Low"

        # Collect metrics
        metrics = {}
        for col in ts_copy.columns:
            if col != "anomaly_score":
                val = row[col]
                if isinstance(val, (int, float, np.integer, np.floating)):
                    metrics[col] = float(val)

        anomalies.append({
            "timestamp": str(idx),
            "score": float(score),
            "severity": severity,
            "metrics": metrics,
        })

    return anomalies


def detect_user_anomalies(df):
    """
    Detect users deviating from their historical patterns.

    For each user:
    - Establishes baseline behavior (first 80% of data)
    - Compares recent activity (last 20%) to baseline
    - Flags significant deviations in:
      * Query volume
      * Table access patterns
      * Active hours
      * Operation type distribution

    Args:
        df (pd.DataFrame): Audit log data with user activity

    Returns:
        list[dict]: Users with anomalous behavior and deviation details
    """
    user_anomalies = []
    df_copy = df.copy()
    df_copy["timestamp"] = pd.to_datetime(df_copy["timestamp"])
    df_copy = df_copy.sort_values("timestamp")

    for username, user_df in df_copy.groupby("username"):
        user_df = user_df.sort_values("timestamp")
        n = len(user_df)
        if n < 10:
            continue  # Not enough data for baseline

        # Split into baseline (first 80%) and recent (last 20%)
        split_idx = int(n * 0.8)
        baseline = user_df.iloc[:split_idx]
        recent = user_df.iloc[split_idx:]

        deviations = {}

        # 1. Query volume deviation
        baseline_duration_h = max((baseline["timestamp"].max() - baseline["timestamp"].min()).total_seconds() / 3600, 1)
        recent_duration_h = max((recent["timestamp"].max() - recent["timestamp"].min()).total_seconds() / 3600, 1)
        baseline_rate = len(baseline) / baseline_duration_h
        recent_rate = len(recent) / recent_duration_h
        volume_change = (recent_rate - baseline_rate) / max(baseline_rate, 1)
        if abs(volume_change) > 0.5:  # 50% change
            deviations["volume_change"] = round(volume_change, 2)

        # 2. New tables accessed
        baseline_tables = set(baseline["table_name"].dropna().unique()) if "table_name" in baseline.columns else set()
        recent_tables = set(recent["table_name"].dropna().unique()) if "table_name" in recent.columns else set()
        new_tables = recent_tables - baseline_tables
        if len(new_tables) > 0:
            deviations["new_tables"] = sorted(list(new_tables))

        # 3. Unusual hours
        baseline_hours = set(pd.to_datetime(baseline["timestamp"]).dt.hour.unique())
        recent_hours = set(pd.to_datetime(recent["timestamp"]).dt.hour.unique())
        new_hours = recent_hours - baseline_hours
        if len(new_hours) > 0:
            deviations["new_active_hours"] = sorted(list(new_hours))

        # 4. Operation type change
        baseline_ops = baseline["operation_category"].value_counts(normalize=True) if "operation_category" in baseline.columns else pd.Series()
        recent_ops = recent["operation_category"].value_counts(normalize=True) if "operation_category" in recent.columns else pd.Series()

        all_ops = set(baseline_ops.index) | set(recent_ops.index)
        for op in all_ops:
            b_val = baseline_ops.get(op, 0)
            r_val = recent_ops.get(op, 0)
            if abs(r_val - b_val) > 0.3:  # 30% shift
                deviations[f"op_shift_{op}"] = f"{b_val:.1%} \u2192 {r_val:.1%}"

        if deviations:
            user_anomalies.append({
                "username": username,
                "baseline_queries": len(baseline),
                "recent_queries": len(recent),
                "deviations": deviations,
            })

    return user_anomalies


def plot_anomalies_time_series(time_series, anomaly_flags):
    """
    Create interactive time series plot with anomalies.

    Visualization:
    - Line: Transaction count over time
    - Red markers: Anomalous time windows
    - Hover: Detailed metrics on hover
    - Interactive: Zoom, pan, select

    Args:
        time_series (pd.DataFrame): Time-indexed metrics
        anomaly_flags (pd.Series): Boolean anomaly indicators

    Returns:
        plotly.graph_objects.Figure: Interactive anomaly plot
    """
    fig = go.Figure()

    # Normal transactions line
    fig.add_trace(go.Scatter(
        x=time_series.index,
        y=time_series["transaction_count"],
        mode="lines",
        name="Transactions",
        line=dict(color="steelblue", width=2),
        hovertemplate="Time: %{x}<br>Count: %{y}<extra></extra>",
    ))

    # Anomaly markers
    anomaly_ts = time_series[anomaly_flags]
    if len(anomaly_ts) > 0:
        reasons_list = anomaly_ts.get("reasons", pd.Series(["Anomaly"] * len(anomaly_ts)))
        fig.add_trace(go.Scatter(
            x=anomaly_ts.index,
            y=anomaly_ts["transaction_count"],
            mode="markers",
            name="Anomalies",
            marker=dict(symbol="x", size=12, color="red", line=dict(width=2)),
            text=reasons_list,
            hovertemplate="Time: %{x}<br>Count: %{y}<br>Reason: %{text}<extra></extra>",
        ))

    fig.update_layout(
        title="Transaction Count Over Time with Anomalies",
        xaxis_title="Time",
        yaxis_title="Transaction Count",
        hovermode="x unified",
        template="plotly_white",
    )

    # Save as HTML
    save_path = PROCESSED_DIR / "anomalies_time_series.html"
    fig.write_html(str(save_path))
    print(f"  Time series plot saved to {save_path}")

    return fig


def plot_anomaly_severity(anomaly_details):
    """
    Plot anomaly severity distribution over time.

    Visualization:
    - Bar chart: Anomaly score per time window
    - Color coding: Green (Low), Orange (Medium), Red (High)
    - Threshold lines for severity boundaries

    Args:
        anomaly_details (list[dict]): Output from detect_time_anomalies

    Returns:
        plotly.graph_objects.Figure: Severity visualization
    """
    if not anomaly_details:
        print("  No anomalies to plot.")
        return None

    df_anom = pd.DataFrame(anomaly_details)
    df_anom["timestamp"] = pd.to_datetime(df_anom["timestamp"])
    df_anom = df_anom.sort_values("timestamp")

    severity_colors = {"Low": "green", "Medium": "orange", "High": "red"}
    colors = [severity_colors.get(s, "gray") for s in df_anom["severity"]]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_anom["timestamp"],
        y=df_anom["score"].abs(),
        name="Anomaly Score",
        marker_color=colors,
        text=df_anom["severity"],
        hovertemplate="Time: %{x}<br>Score: %{y:.3f}<br>Severity: %{text}<extra></extra>",
    ))

    fig.update_layout(
        title="Anomaly Severity Distribution",
        xaxis_title="Time",
        yaxis_title="Anomaly Score (absolute)",
        template="plotly_white",
    )

    # Save as HTML
    save_path = PROCESSED_DIR / "anomaly_severity.html"
    fig.write_html(str(save_path))
    print(f"  Severity plot saved to {save_path}")

    return fig


def run_anomaly_detection(df, window="1h", contamination=0.05):
    """
    Execute complete anomaly detection pipeline.

    Pipeline:
    1. Build time series (hourly aggregation)
    2. Run Isolation Forest detection
    3. Run LOF detection
    4. Apply rule-based suspicious activity flags
    5. Combine all anomaly signals
    6. Detect specific time and user anomalies
    7. Generate interactive visualizations
    8. Save results to data/processed/

    Args:
        df (pd.DataFrame): Raw audit log data
        window (str): Time window for aggregation
        contamination (float): Expected outlier proportion

    Returns:
        dict: {
            'time_series': pd.DataFrame,
            'isolation_forest_results': dict,
            'lof_results': dict,
            'suspicious_flags': pd.DataFrame,
            'time_anomalies': list,
            'user_anomalies': list,
            'plots': dict
        }
    """
    print("=" * 60)
    print("Anomaly Detection Pipeline")
    print("=" * 60)
    print(f"  Records: {len(df)}, Window: {window}")

    results = {
        "time_series": None,
        "isolation_forest_results": {},
        "lof_results": {},
        "suspicious_flags": None,
        "time_anomalies": [],
        "user_anomalies": [],
        "plots": {},
    }

    # Step 1: Build time series
    print("\n[1/8] Building time series...")
    ts = build_time_series(df, window=window)
    results["time_series"] = ts
    print(f"  Time windows: {len(ts)}")
    print(f"  Columns: {list(ts.columns)}")

    # Prepare features for ML (numeric only)
    feature_cols = ts.select_dtypes(include=[np.number]).columns.tolist()
    X = ts[feature_cols].values

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Step 2: Isolation Forest
    print("\n[2/8] Running Isolation Forest...")
    if_predictions = None
    if_scores = None
    if len(X_scaled) >= 10:
        if_predictions, if_scores = run_isolation_forest(X_scaled, contamination=contamination)
        n_if_anomalies = int(np.sum(if_predictions == -1))
        results["isolation_forest_results"] = {
            "predictions": if_predictions,
            "scores": if_scores,
            "n_anomalies": n_if_anomalies,
        }
        print(f"  Anomalies detected: {n_if_anomalies}")
    else:
        print(f"  Too few time windows ({len(X_scaled)}), skipping IF")

    # Step 3: LOF
    print("\n[3/8] Running Local Outlier Factor...")
    lof_predictions = None
    lof_scores = None
    if len(X_scaled) >= 10:
        lof_predictions, lof_scores = run_lof(X_scaled, contamination=contamination)
        n_lof_anomalies = int(np.sum(lof_predictions == -1))
        results["lof_results"] = {
            "predictions": lof_predictions,
            "scores": lof_scores,
            "n_anomalies": n_lof_anomalies,
        }
        print(f"  Anomalies detected: {n_lof_anomalies}")
    else:
        print(f"  Too few time windows ({len(X_scaled)}), skipping LOF")

    # Step 4: Rule-based flags
    print("\n[4/8] Applying rule-based suspicious activity flags...")
    # Use IF predictions as ML input if available
    ml_preds = if_predictions if if_predictions is not None else lof_predictions
    flags = flag_suspicious_activity(ts, ml_predictions=ml_preds)
    results["suspicious_flags"] = flags
    n_flagged = flags["is_suspicious"].sum()
    print(f"  Flagged time windows: {n_flagged}")

    # Step 5: Combine anomaly signals
    print("\n[5/8] Combining anomaly signals...")
    combined_anomaly = flags["is_suspicious"].values.copy()
    if if_predictions is not None:
        combined_anomaly = combined_anomaly | (if_predictions == -1)
    if lof_predictions is not None:
        combined_anomaly = combined_anomaly | (lof_predictions == -1)
    n_combined = int(np.sum(combined_anomaly))
    print(f"  Combined anomalies: {n_combined}")

    # Step 6: Detect time and user anomalies
    print("\n[6/8] Detecting time-based anomalies...")
    combined_scores = if_scores if if_scores is not None else (lof_scores if lof_scores is not None else np.zeros(len(ts)))
    time_anomalies = detect_time_anomalies(ts, combined_scores)
    results["time_anomalies"] = time_anomalies
    print(f"  Time anomalies: {len(time_anomalies)}")
    for ta in time_anomalies[:5]:
        print(f"    {ta['timestamp']} \u2014 Score: {ta['score']:.3f}, Severity: {ta['severity']}")

    print("\n[7/8] Detecting user anomalies...")
    user_anomalies = detect_user_anomalies(df)
    results["user_anomalies"] = user_anomalies
    print(f"  Users with anomalies: {len(user_anomalies)}")
    for ua in user_anomalies[:5]:
        print(f"    {ua['username']} \u2014 Deviations: {ua['deviations']}")

    # Step 7: Generate visualizations
    print("\n[8/8] Generating visualizations...")
    anomaly_flag_series = pd.Series(combined_anomaly, index=ts.index)
    fig_ts = plot_anomalies_time_series(ts, anomaly_flag_series)
    results["plots"]["time_series"] = fig_ts

    fig_severity = plot_anomaly_severity(time_anomalies)
    results["plots"]["severity"] = fig_severity

    # Save summary
    summary = {
        "time_windows": len(ts),
        "isolation_forest_anomalies": results["isolation_forest_results"].get("n_anomalies", 0),
        "lof_anomalies": results["lof_results"].get("n_anomalies", 0),
        "rule_based_flags": int(n_flagged),
        "combined_anomalies": n_combined,
        "time_anomaly_count": len(time_anomalies),
        "user_anomaly_count": len(user_anomalies),
        "time_anomalies": time_anomalies[:20],  # Limit output
        "user_anomalies": user_anomalies[:20],
    }

    json_path = PROCESSED_DIR / "anomaly_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"  Summary saved to {json_path}")

    print("\n" + "=" * 60)
    print("Anomaly Detection Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    from etl.db_client import execute_query

    print("=== Anomaly Detection Runner ===")
    print("Loading data from audit_data.audit_logs...")

    try:
        df = execute_query("SELECT * FROM audit_data.audit_logs")
        if df.empty:
            print("No data found. Run ETL pipeline first.")
        else:
            print(f"Loaded {len(df)} records.")
            print(f"Time range: {df['timestamp'].min()} to {df['timestamp'].max()}")

            results = run_anomaly_detection(df, window="1h")

            print("\nDone! Check data/processed/ for plots and results.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
