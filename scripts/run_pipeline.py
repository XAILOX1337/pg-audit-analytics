import os
import sys
import argparse
import time

import pandas as pd

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "etl"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "analytics"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))

from db_client import execute_query, get_table_count
from loader import run_etl_pipeline
from feature_eng import prepare_for_clustering
from clustering import run_clustering_analysis
from anomaly_detection import run_anomaly_detection
from query_analysis import generate_query_report


def run_full_pipeline(generate_data=True, duration_hours=24, replace=False):
    """
    Execute the complete analytics pipeline.

    Pipeline stages:
    1. Data Generation: Simulate database workload (CSV logs)
    2. ETL: Parse CSV logs and load to PostgreSQL
    3. Feature Engineering: Build feature matrices
    4. Clustering: Run KMeans and DBSCAN
    5. Anomaly Detection: Run Isolation Forest and LOF
    6. Query Analysis: Performance degradation

    Args:
        generate_data (bool): Run load generator first
        duration_hours (int): Simulation duration for load generator
        replace (bool): Replace existing data in DB

    Returns:
        dict: {
            'etl_stats': dict,
            'clustering_results': dict,
            'anomaly_results': dict,
            'query_report': dict,
            'pipeline_duration': float
        }
    """
    start_time = time.time()
    results = {}

    print("\n" + "#" * 60)
    print("#  pg-audit-analytics — Full Pipeline")
    print("#" * 60)

    # ------------------------------------------------------------------
    # Stage 1: Generate test data — execute directly against PostgreSQL
    # ------------------------------------------------------------------
    if generate_data:
        print("\n" + "=" * 60)
        print("Stage 1: Load Generation (direct PostgreSQL)")
        print("=" * 60)
        from load_generator import run_load_simulation

        # Convert hours to minutes for the new generator
        duration_minutes = max(duration_hours * 60, 5)
        gen_stats = run_load_simulation(duration_minutes=duration_minutes)
        results["generation"] = gen_stats
        print(f"  {gen_stats['total_queries']} queries executed against PostgreSQL")
        print(f"  Logs written to PostgreSQL CSV log directory")
    else:
        print("\n  Skipping load generation (using existing PostgreSQL logs)")

    # ------------------------------------------------------------------
    # Stage 2: ETL
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 2: ETL Pipeline")
    print("=" * 60)

    etl_stats = run_etl_pipeline(max_files=1, replace=replace)
    results["etl"] = etl_stats

    # ------------------------------------------------------------------
    # Stage 3: Load data from DB for analytics
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 3: Loading data from database")
    print("=" * 60)

    df = execute_query("SELECT * FROM audit_data.audit_logs")
    n_users = df["username"].nunique() if not df.empty else 0
    print(f"  Records in audit_logs: {len(df)}")
    print(f"  Unique users: {n_users}")

    if df.empty:
        print("  No data in database. Aborting analytics.")
        results["pipeline_duration"] = time.time() - start_time
        return results

    # ------------------------------------------------------------------
    # Stage 4: Feature Engineering
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 4: Feature Engineering")
    print("=" * 60)

    if n_users >= 2:
        X_scaled, user_ids, feature_names, scaler = prepare_for_clustering(df)
        results["features"] = {
            "n_users": n_users,
            "n_features": len(feature_names),
            "feature_names": feature_names,
        }
        print(f"  Feature matrix: {X_scaled.shape}")
        print(f"  Features: {len(feature_names)}")
    else:
        print(f"  ⚠ Only {n_users} user(s) — skipping feature engineering (need ≥ 2)")
        X_scaled, user_ids, feature_names, scaler = None, None, None, None

    # ------------------------------------------------------------------
    # Stage 5: Clustering
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 5: Clustering Analysis")
    print("=" * 60)

    if X_scaled is not None and len(X_scaled) >= 2:
        clustering = run_clustering_analysis(X_scaled, feature_names, user_ids)
        results["clustering"] = clustering
    else:
        print("  ⚠ Skipping clustering — insufficient data")
        results["clustering"] = {"skipped": True}

    # ------------------------------------------------------------------
    # Stage 6: Anomaly Detection
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 6: Anomaly Detection")
    print("=" * 60)

    anomaly = run_anomaly_detection(df, window="1h")
    results["anomaly"] = anomaly

    # ------------------------------------------------------------------
    # Stage 7: Query Performance Analysis
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Stage 7: Query Performance Analysis")
    print("=" * 60)

    query_report = generate_query_report(df)
    results["query_report"] = query_report

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time
    results["pipeline_duration"] = elapsed

    print("\n" + "#" * 60)
    print(f"#  Pipeline Complete — {elapsed:.1f}s")
    print("#" * 60)

    return results


def print_pipeline_summary(results):
    """
    Print formatted pipeline execution summary.

    Args:
        results (dict): Output from run_full_pipeline
    """
    print("\n" + "=" * 60)
    print("Pipeline Summary")
    print("=" * 60)

    # Generation
    if "generation" in results:
        g = results["generation"]
        print(f"\n  Load Generation:")
        print(f"    Total queries:     {g.get('total_queries', 0)}")
        print(f"    Normal:            {g.get('normal_queries', 0)}")
        print(f"    Suspicious:        {g.get('suspicious_queries', 0)}")
        print(f"    Log file:          {g.get('log_file', 'N/A')}")

    # ETL
    if "etl" in results:
        e = results["etl"]
        print(f"\n  ETL:")
        print(f"    Records parsed:    {e.get('parsed', 0)}")
        print(f"    Records loaded:    {e.get('loaded', 0)}")
        agg = e.get("aggregations", {})
        print(f"    User activity:     {agg.get('user_activity', 0)} rows")
        print(f"    Query stats:       {agg.get('query_stats', 0)} rows")

    # Clustering
    if "clustering" in results and not results["clustering"].get("skipped"):
        c = results["clustering"]
        m = c.get("metrics", {})
        print(f"\n  Clustering:")
        print(f"    Optimal K:         {m.get('optimal_k', 'N/A')}")
        km = m.get("kmeans", {})
        if km.get("silhouette") is not None:
            print(f"    Silhouette:        {km['silhouette']:.3f}")
            print(f"    Davies-Bouldin:    {km['davies_bouldin']:.3f}")
        sem = c.get("semantic_labels", {})
        if sem:
            for cid, label in sem.items():
                print(f"    Cluster {cid} → {label}")

    # Anomaly Detection
    if "anomaly" in results:
        a = results["anomaly"]
        flags = a.get("suspicious_flags")
        if flags is not None and isinstance(flags, pd.DataFrame):
            n_flagged = int(flags["is_suspicious"].sum())
        else:
            n_flagged = "N/A"
        print(f"\n  Anomaly Detection:")
        print(f"    IF anomalies:      {a.get('isolation_forest_results', {}).get('n_anomalies', 0)}")
        print(f"    LOF anomalies:     {a.get('lof_results', {}).get('n_anomalies', 0)}")
        print(f"    Combined:          {n_flagged}")
        print(f"    Time anomalies:    {len(a.get('time_anomalies', []))}")
        print(f"    User anomalies:    {len(a.get('user_anomalies', []))}")

    # Query Report
    if "query_report" in results:
        qr = results["query_report"]
        s = qr.get("summary", {})
        print(f"\n  Query Performance:")
        print(f"    Total queries:     {s.get('total_queries', 0)}")
        print(f"    Mean:              {s.get('mean_ms', 0):.2f} ms")
        print(f"    P95:               {s.get('p95_ms', 0):.2f} ms")
        print(f"    P99:               {s.get('p99_ms', 0):.2f} ms")
        slow = qr.get("slow_queries")
        if slow is not None and isinstance(slow, pd.DataFrame) and not slow.empty:
            print(f"    Slow queries:      {len(slow)}")
        deg = qr.get("degradation")
        if deg is not None and isinstance(deg, pd.DataFrame) and not deg.empty:
            degrading = int(deg["is_degrading"].sum())
            print(f"    Degrading queries: {degrading}")

    # Duration
    if "pipeline_duration" in results:
        print(f"\n  Total duration:      {results['pipeline_duration']:.1f}s")

    print("\n" + "=" * 60)
    print("Check data/processed/ for plots and JSON reports.")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run pg-audit-analytics pipeline")
    parser.add_argument(
        "--mode",
        choices=["full", "etl-only", "analytics"],
        default="full",
        help="Pipeline execution mode"
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=1,
        help="Simulation duration in hours (for load generation)"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing data in database"
    )
    args = parser.parse_args()

    if args.mode == "full":
        results = run_full_pipeline(
            generate_data=True,
            duration_hours=args.hours,
            replace=args.replace,
        )
        print_pipeline_summary(results)

    elif args.mode == "etl-only":
        print("Running ETL pipeline only...")
        etl_stats = run_etl_pipeline(max_files=1, replace=args.replace)
        print(f"\nETL Result: {etl_stats}")

    elif args.mode == "analytics":
        print("Running analytics only (data must already be in DB)...")

        df = execute_query("SELECT * FROM audit_data.audit_logs")
        if df.empty:
            print("No data found. Run ETL first.")
            sys.exit(1)

        n_users = df["username"].nunique()
        print(f"Loaded {len(df)} records, {n_users} users.")

        # Feature engineering
        if n_users >= 2:
            X_scaled, user_ids, feature_names, scaler = prepare_for_clustering(df)
            run_clustering_analysis(X_scaled, feature_names, user_ids)
        else:
            print(f"Skipping clustering ({n_users} user, need ≥ 2)")

        # Anomaly detection
        run_anomaly_detection(df, window="1h")

        # Query analysis
        generate_query_report(df)

        print("\nAnalytics complete. Check data/processed/ for results.")

