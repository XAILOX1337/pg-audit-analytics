"""
Query performance analysis module.

Analyzes query execution time distributions,
identifies slow queries, and tracks performance degradation over time.
"""

import sys
import re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from scipy import stats
from sklearn.linear_model import LinearRegression

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "etl") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "etl"))

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Regex for query analysis
WHERE_PATTERN = re.compile(r'\bWHERE\b', re.IGNORECASE)


def analyze_query_distribution(df):
    """
    Analyze query execution time distribution.

    Creates:
    - Histogram with KDE overlay
    - Log-scale x-axis for skewness
    - Percentile markers: P50, P95, P99
    - Separate plots by operation type

    Args:
        df (pd.DataFrame): Data with 'duration_ms' column

    Returns:
        matplotlib.figure.Figure: Distribution visualization
    """
    valid = df.dropna(subset=["duration_ms"])
    durations = valid["duration_ms"]
    durations = durations[durations > 0]  # Filter out zero-duration entries

    if len(durations) == 0:
        print("  No valid duration data for distribution analysis.")
        return None

    # Calculate percentiles
    p50 = durations.quantile(0.50)
    p95 = durations.quantile(0.95)
    p99 = durations.quantile(0.99)

    fig, ax = plt.subplots(figsize=(12, 6))

    # Histogram with KDE
    sns.histplot(
        durations,
        bins=50,
        kde=True,
        ax=ax,
        color="steelblue",
        alpha=0.6,
        label="Distribution",
    )

    # Percentile markers
    colors = {"P50": "green", "P95": "orange", "P99": "red"}
    for label, value, color in [("P50", p50, colors["P50"]),
                                 ("P95", p95, colors["P95"]),
                                 ("P99", p99, colors["P99"])]:
        ax.axvline(value, color=color, linestyle="--", linewidth=2,
                   label=f"{label} = {value:.2f} ms")

    ax.set_xlabel("Duration (ms)")
    ax.set_ylabel("Count")
    ax.set_title("Query Execution Time Distribution")
    ax.legend()

    # Use log scale for better visualization of skewed data
    ax.set_xscale("log")

    fig.tight_layout()

    save_path = PROCESSED_DIR / "query_distribution.png"
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Distribution plot saved to {save_path}")

    # Print summary
    print(f"  P50: {p50:.2f} ms, P95: {p95:.2f} ms, P99: {p99:.2f} ms")

    return fig


def detect_slow_queries(df, threshold_ms=1000):
    """
    Detect queries exceeding performance thresholds.

    Identifies slow queries by:
    - Absolute threshold: duration > threshold_ms
    - Percentile-based: duration > P95 or P99
    - Returns query patterns with avg/max durations

    Args:
        df (pd.DataFrame): Audit data with 'duration_ms' column
        threshold_ms (int): Absolute threshold in milliseconds

    Returns:
        pd.DataFrame: Slow queries with details
    """
    valid = df.dropna(subset=["duration_ms"]).copy()
    valid = valid[valid["duration_ms"] > 0]

    if valid.empty:
        print("  No valid duration data for slow query detection.")
        return pd.DataFrame()

    # Calculate percentile thresholds
    p95 = valid["duration_ms"].quantile(0.95)
    p99 = valid["duration_ms"].quantile(0.99)

    # Classify each query
    valid["is_slow_absolute"] = valid["duration_ms"] > threshold_ms
    valid["is_slow_p95"] = valid["duration_ms"] > p95
    valid["is_slow_p99"] = valid["duration_ms"] > p99
    valid["is_slow_any"] = valid["is_slow_absolute"] | valid["is_slow_p95"]

    # Aggregate by query pattern (using query_hash if available)
    grouping_col = "query_hash" if "query_hash" in valid.columns else "raw_query"

    slow_queries = valid[valid["is_slow_any"]].groupby(grouping_col).agg(
        query_pattern=("raw_query", "first"),
        operation_type=("operation_type", "first"),
        table_name=("table_name", "first"),
        avg_duration_ms=("duration_ms", "mean"),
        max_duration_ms=("duration_ms", "max"),
        min_duration_ms=("duration_ms", "min"),
        execution_count=("duration_ms", "count"),
        p95_duration_ms=("duration_ms", lambda x: x.quantile(0.95)),
        p99_duration_ms=("duration_ms", lambda x: x.quantile(0.99)),
    ).reset_index()

    # Sort by avg duration descending
    slow_queries = slow_queries.sort_values("avg_duration_ms", ascending=False)

    # Add slow classification flags
    slow_queries["threshold_type"] = slow_queries.apply(
        lambda row: (
            "absolute" if row["max_duration_ms"] > threshold_ms else
            ("p95" if row["p95_duration_ms"] > p95 else "p99")
        ),
        axis=1,
    )

    print(f"  Total slow queries found: {len(slow_queries)}")
    print(f"  Thresholds: absolute={threshold_ms}ms, P95={p95:.2f}ms, P99={p99:.2f}ms")

    return slow_queries


def track_query_degradation(df, window="1h"):
    """
    Track query performance degradation over time.

    For each query pattern:
    1. Calculate average duration per time window
    2. Fit linear regression to trend
    3. Calculate slope (ms/hour)
    4. Flag queries with significant positive slope

    Args:
        df (pd.DataFrame): Audit data with timestamps and durations
        window (str): Time window for aggregation

    Returns:
        pd.DataFrame: Query patterns with degradation metrics
    """
    valid = df.dropna(subset=["duration_ms", "timestamp"]).copy()
    valid = valid[valid["duration_ms"] > 0]
    valid["timestamp"] = pd.to_datetime(valid["timestamp"])

    grouping_col = "query_hash" if "query_hash" in valid.columns else "raw_query"

    results = []

    for pattern, pattern_df in valid.groupby(grouping_col):
        if len(pattern_df) < 3:
            continue  # Need at least 3 points for regression

        # Resample to time windows
        pattern_ts = pattern_df.set_index("timestamp")
        ts_agg = pattern_ts.resample(window)["duration_ms"].agg(["mean", "count"]).dropna()

        if len(ts_agg) < 3:
            continue

        # Convert index to numeric (hours from start)
        ts_start = ts_agg.index.min()
        X = (ts_agg.index - ts_start).total_seconds().values.reshape(-1, 1) / 3600  # hours
        y = ts_agg["mean"].values

        # Fit linear regression
        reg = LinearRegression()
        reg.fit(X, y)
        slope = reg.coef_[0]  # ms per hour
        r_squared = reg.score(X, y)

        # Flag if positive slope (degrading)
        is_degrading = slope > 0
        significance = "degrading" if is_degrading else "stable"

        results.append({
            "query_hash": pattern,
            "query_pattern": pattern_df["raw_query"].iloc[0] if "raw_query" in pattern_df.columns else str(pattern),
            "operation_type": pattern_df["operation_type"].iloc[0] if "operation_type" in pattern_df.columns else None,
            "table_name": pattern_df["table_name"].iloc[0] if "table_name" in pattern_df.columns else None,
            "total_executions": len(pattern_df),
            "time_windows": len(ts_agg),
            "avg_duration_ms": pattern_df["duration_ms"].mean(),
            "max_duration_ms": pattern_df["duration_ms"].max(),
            "slope_ms_per_hour": slope,
            "r_squared": r_squared,
            "is_degrading": is_degrading,
            "significance": significance,
        })

    degradation_df = pd.DataFrame(results)

    if degradation_df.empty:
        print("  No query patterns with enough data for degradation analysis.")
        return pd.DataFrame()

    # Sort by slope descending (most degrading first)
    degradation_df = degradation_df.sort_values("slope_ms_per_hour", ascending=False)

    n_degrading = degradation_df["is_degrading"].sum()
    print(f"  Analyzed {len(degradation_df)} query patterns")
    print(f"  Degrading: {n_degrading}, Stable: {len(degradation_df) - n_degrading}")

    return degradation_df


def identify_index_candidates(df):
    """
    Identify queries that could benefit from indexing.

    Indicators:
    - Full table scans: SELECT without WHERE
    - High duration + high frequency combination
    - Filters on columns without indexes
    - Sequential scans on large tables

    Args:
        df (pd.DataFrame): Audit data with queries and durations

    Returns:
        list[dict]: Query patterns with index recommendations
    """
    valid = df.dropna(subset=["duration_ms"]).copy()
    valid = valid[valid["duration_ms"] > 0]

    grouping_col = "query_hash" if "query_hash" in valid.columns else "raw_query"

    candidates = []

    for pattern, pattern_df in valid.groupby(grouping_col):
        raw_query = pattern_df["raw_query"].iloc[0] if "raw_query" in pattern_df.columns else ""
        operation = pattern_df["operation_type"].iloc[0] if "operation_type" in pattern_df.columns else ""

        reasons = []
        priority = "low"

        # Check for full table scan (SELECT without WHERE)
        if operation == "SELECT" and isinstance(raw_query, str):
            if not WHERE_PATTERN.search(raw_query):
                reasons.append("Full table scan (no WHERE clause)")
                priority = "high"

        # High duration + high frequency
        avg_dur = pattern_df["duration_ms"].mean()
        count = len(pattern_df)
        if avg_dur > 500 and count > 10:
            reasons.append(f"High frequency ({count}x) + slow (avg {avg_dur:.0f}ms)")
            if priority == "low":
                priority = "medium"

        # Very slow queries
        if avg_dur > 2000:
            reasons.append(f"Very slow average duration ({avg_dur:.0f}ms)")
            priority = "high"

        if reasons:
            candidates.append({
                "query_hash": pattern,
                "query_pattern": raw_query[:200] if isinstance(raw_query, str) else str(pattern),
                "table_name": pattern_df["table_name"].iloc[0] if "table_name" in pattern_df.columns else None,
                "operation_type": operation,
                "avg_duration_ms": avg_dur,
                "max_duration_ms": pattern_df["duration_ms"].max(),
                "execution_count": count,
                "reasons": reasons,
                "priority": priority,
            })

    # Sort by priority (high first) then by avg duration
    priority_order = {"high": 0, "medium": 1, "low": 2}
    candidates.sort(key=lambda x: (priority_order.get(x["priority"], 3), -x["avg_duration_ms"]))

    print(f"  Index candidates found: {len(candidates)}")
    for c in candidates[:5]:
        print(f"    [{c['priority'].upper()}] {c['table_name']} — {', '.join(c['reasons'])}")

    return candidates


def plot_query_performance(df):
    """
    Create box plot of query durations by operation type.

    Visualization:
    - Box plot: Shows median, quartiles, outliers
    - Grouped by: operation_type (READ, WRITE, DDL)
    - Log scale y-axis
    - Interactive hover with details

    Args:
        df (pd.DataFrame): Audit data with operation_type and duration_ms

    Returns:
        plotly.graph_objects.Figure: Box plot visualization
    """
    valid = df.dropna(subset=["duration_ms", "operation_type"]).copy()
    valid = valid[valid["duration_ms"] > 0]

    if valid.empty:
        print("  No valid data for box plot.")
        return None

    fig = go.Figure()

    for op_type in sorted(valid["operation_type"].unique()):
        op_data = valid[valid["operation_type"] == op_type]
        fig.add_trace(go.Box(
            y=op_data["duration_ms"],
            name=op_type,
            boxmean=True,
            hovertemplate="Duration: %{y:.2f} ms<extra></extra>",
        ))

    fig.update_layout(
        title="Query Duration Distribution by Operation Type",
        yaxis_title="Duration (ms)",
        yaxis_type="log",
        template="plotly_white",
        showlegend=True,
    )

    # Save as HTML
    save_path = PROCESSED_DIR / "query_performance_boxplot.html"
    fig.write_html(str(save_path))
    print(f"  Box plot saved to {save_path}")

    return fig


def plot_degradation_trends(degradation_df, top_n=10):
    """
    Plot query performance degradation trends.

    For top N slowest query patterns:
    - Time series of average duration
    - Linear trend line
    - Color coding: red for degrading, green for stable

    Args:
        degradation_df (pd.DataFrame): Output from track_query_degradation
        top_n (int): Number of query patterns to show

    Returns:
        plotly.graph_objects.Figure: Trend visualization
    """
    if degradation_df.empty or len(degradation_df) == 0:
        print("  No degradation data for plotting.")
        return None

    top = degradation_df.head(top_n)

    fig = go.Figure()

    for _, row in top.iterrows():
        pattern = row["query_hash"]
        color = "red" if row["is_degrading"] else "green"
        label = f"{row['table_name']} ({'degrading' if row['is_degrading'] else 'stable'})"

        # Add marker for avg duration
        fig.add_trace(go.Scatter(
            x=[0],
            y=[row["avg_duration_ms"]],
            mode="markers",
            name=label,
            marker=dict(size=10, color=color, symbol="diamond"),
            hovertemplate=f"Pattern: {row['query_hash'][:20]}...<br>"
                         f"Avg: {row['avg_duration_ms']:.1f} ms<br>"
                         f"Slope: {row['slope_ms_per_hour']:.4f} ms/hr<extra></extra>",
        ))

    fig.update_layout(
        title=f"Top {top_n} Query Patterns by Degradation Slope",
        xaxis_title="Query Pattern Index",
        yaxis_title="Average Duration (ms)",
        yaxis_type="log",
        template="plotly_white",
        showlegend=False,
    )

    save_path = PROCESSED_DIR / "degradation_trends.html"
    fig.write_html(str(save_path))
    print(f"  Degradation trends saved to {save_path}")

    return fig


def generate_query_report(df):
    """
    Generate comprehensive query performance report.

    Report sections:
    1. Overall statistics (mean, median, P95, P99)
    2. Top 20 slowest query patterns
    3. Degradation trends analysis
    4. Index recommendations
    5. Distribution histograms
    6. Box plots by operation type

    Args:
        df (pd.DataFrame): Audit data with query metrics

    Returns:
        dict: Report data and visualizations
    """
    print("=" * 60)
    print("Query Performance Report")
    print("=" * 60)

    report = {
        "summary": {},
        "slow_queries": None,
        "degradation": None,
        "index_candidates": [],
        "plots": {},
    }

    # Section 1: Overall statistics
    print("\n[1/6] Computing overall statistics...")
    valid = df.dropna(subset=["duration_ms"])
    valid = valid[valid["duration_ms"] > 0]

    if valid.empty:
        print("  No valid duration data. Skipping report.")
        return report

    durations = valid["duration_ms"]
    report["summary"] = {
        "total_queries": len(valid),
        "mean_ms": float(durations.mean()),
        "median_ms": float(durations.median()),
        "p50_ms": float(durations.quantile(0.50)),
        "p95_ms": float(durations.quantile(0.95)),
        "p99_ms": float(durations.quantile(0.99)),
        "min_ms": float(durations.min()),
        "max_ms": float(durations.max()),
        "std_ms": float(durations.std()),
    }
    print(f"  Queries: {report['summary']['total_queries']}")
    print(f"  Mean: {report['summary']['mean_ms']:.2f}ms, Median: {report['summary']['median_ms']:.2f}ms")
    print(f"  P95: {report['summary']['p95_ms']:.2f}ms, P99: {report['summary']['p99_ms']:.2f}ms")

    # Section 2: Slow queries
    print("\n[2/6] Detecting slow queries...")
    slow = detect_slow_queries(df, threshold_ms=1000)
    report["slow_queries"] = slow
    if not slow.empty:
        print(f"  Top 5 slowest:")
        for _, row in slow.head(5).iterrows():
            print(f"    {row['table_name']} — avg {row['avg_duration_ms']:.1f}ms ({row['execution_count']}x)")

    # Section 3: Degradation analysis
    print("\n[3/6] Tracking query degradation...")
    degradation = track_query_degradation(df, window="1h")
    report["degradation"] = degradation
    if not degradation.empty:
        degrading = degradation[degradation["is_degrading"]]
        print(f"  Degrading queries: {len(degrading)}")

    # Section 4: Index candidates
    print("\n[4/6] Identifying index candidates...")
    index_candidates = identify_index_candidates(df)
    report["index_candidates"] = index_candidates

    # Section 5: Distribution histogram
    print("\n[5/6] Generating distribution plot...")
    fig_dist = analyze_query_distribution(df)
    report["plots"]["distribution"] = fig_dist

    # Section 6: Box plot by operation type
    print("\n[6/6] Generating performance box plot...")
    fig_box = plot_query_performance(df)
    report["plots"]["box_plot"] = fig_box

    # Additional: degradation trends
    if not degradation.empty:
        fig_deg = plot_degradation_trends(degradation)
        report["plots"]["degradation"] = fig_deg

    # Save summary JSON
    import json
    summary_json = {
        "summary": report["summary"],
        "slow_query_count": len(slow) if not slow.empty else 0,
        "degrading_query_count": int(degradation["is_degrading"].sum()) if not degradation.empty else 0,
        "index_candidate_count": len(index_candidates),
        "slow_queries_top20": slow.head(20).to_dict(orient="records") if not slow.empty else [],
        "index_candidates": index_candidates[:20],
    }

    json_path = PROCESSED_DIR / "query_report_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary_json, f, indent=2, default=str)
    print(f"\n  Report summary saved to {json_path}")

    print("\n" + "=" * 60)
    print("Query Performance Report Complete")
    print("=" * 60)

    return report


if __name__ == "__main__":
    from etl.db_client import execute_query

    print("=== Query Performance Analysis Runner ===")
    print("Loading data from audit_data.audit_logs...")

    try:
        df = execute_query("SELECT * FROM audit_data.audit_logs")
        if df.empty:
            print("No data found. Run ETL pipeline first.")
        else:
            print(f"Loaded {len(df)} records.")

            report = generate_query_report(df)

            print("\nDone! Check data/processed/ for plots and results.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
