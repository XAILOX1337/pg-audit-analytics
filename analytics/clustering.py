"""
Clustering module for user behavior analysis.

Implements K-Means and DBSCAN algorithms to group
database users by their activity patterns.
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.cluster import KMeans, DBSCAN
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score, davies_bouldin_score

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "etl") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "etl"))

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Semantic label rules based on feature patterns
NIGHT_HOUR_FEATURES = [f"hour_{h}" for h in range(0, 7)]  # 0-6 AM
BUSINESS_HOUR_FEATURES = [f"hour_{h}" for h in range(8, 18)]  # 8 AM - 5 PM
OPERATION_RATIO_FEATURES = ["read_ratio", "write_ratio", "ddl_ratio", "dcl_ratio"]


def run_kmeans(X, n_clusters=4, random_state=42):
    """
    Perform K-Means clustering on scaled features.

    Args:
        X (np.ndarray): Scaled feature matrix (n_users, n_features)
        n_clusters (int): Number of clusters (k)
        random_state (int): Reproducibility seed

    Returns:
        tuple: (
            labels: np.ndarray (cluster assignment per user),
            model: fitted KMeans instance,
            inertia: float (within-cluster sum of squares)
        )
    """
    model = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10, max_iter=300)
    labels = model.fit_predict(X)
    inertia = model.inertia_
    return labels, model, inertia


def find_optimal_k(X, k_range=range(2, 11)):
    """
    Find optimal number of clusters using elbow method.

    Evaluates KMeans for different k values and:
    - Plots inertia (WCSS) vs k
    - Calculates silhouette scores
    - Suggests optimal k based on silhouette score maximum

    Args:
        X (np.ndarray): Scaled feature matrix
        k_range (range): Range of k values to test

    Returns:
        tuple: (optimal_k: int, inertias: list, silhouette_scores: list)
    """
    inertias = []
    sil_scores = []

    for k in k_range:
        _, model, inertia = run_kmeans(X, n_clusters=k)
        inertias.append(inertia)

        # Silhouette score requires at least 2 clusters and fewer clusters than samples
        if 1 < k < len(X):
            labels = model.labels_
            sil = silhouette_score(X, labels)
            sil_scores.append(sil)
        else:
            sil_scores.append(0.0)

    # Plot elbow curve
    fig, ax1 = plt.subplots(figsize=(10, 5))

    color = "tab:blue"
    ax1.set_xlabel("Number of Clusters (k)")
    ax1.set_ylabel("Inertia (WCSS)", color=color)
    ax1.plot(list(k_range), inertias, marker="o", color=color)
    ax1.tick_params(axis="y", labelcolor=color)

    color = "tab:red"
    ax2 = ax1.twinx()
    ax2.set_ylabel("Silhouette Score", color=color)
    ax2.plot(list(k_range), sil_scores, marker="s", color=color, linestyle="--")
    ax2.tick_params(axis="y", labelcolor=color)

    plt.title("Elbow Method: Inertia & Silhouette Score vs K")
    fig.tight_layout()

    save_path = PROCESSED_DIR / "elbow_curve.png"
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Elbow curve saved to {save_path}")

    # Suggest optimal k based on best silhouette score
    best_idx = np.argmax(sil_scores)
    optimal_k = list(k_range)[best_idx]

    return optimal_k, inertias, sil_scores


def run_dbscan(X, eps=0.5, min_samples=5):
    """
    Perform DBSCAN clustering on scaled features.

    Density-based clustering that:
    - Automatically determines number of clusters
    - Identifies outliers as noise (label = -1)
    - Finds arbitrarily shaped clusters

    Args:
        X (np.ndarray): Scaled feature matrix
        eps (float): Maximum distance for neighborhood
        min_samples (int): Minimum points for dense region

    Returns:
        tuple: (labels: np.ndarray, model: fitted DBSCAN)
    """
    model = DBSCAN(eps=eps, min_samples=min_samples)
    labels = model.fit_predict(X)
    return labels, model


def evaluate_clusters(X, labels):
    """
    Evaluate clustering quality with multiple metrics.

    Metrics computed:
    - silhouette_score: Cohesion vs separation (-1 to 1, higher is better)
    - davies_bouldin_score: Cluster separation (lower is better)
    - n_clusters: Number of discovered clusters
    - cluster_sizes: Distribution of points per cluster
    - noise_ratio: Percentage of outliers (for DBSCAN)

    Args:
        X (np.ndarray): Feature matrix
        labels (np.ndarray): Cluster assignments

    Returns:
        dict: {
            'silhouette': float,
            'davies_bouldin': float,
            'n_clusters': int,
            'cluster_sizes': dict,
            'noise_ratio': float (DBSCAN only)
        }
    """
    unique_labels = np.unique(labels)
    n_clusters = len(unique_labels[unique_labels != -1])
    noise_count = np.sum(labels == -1)
    noise_ratio = noise_count / len(labels) if len(labels) > 0 else 0.0

    metrics = {
        "n_clusters": n_clusters,
        "cluster_sizes": {},
        "noise_ratio": noise_ratio,
    }

    # Cluster sizes
    for lbl in unique_labels:
        count = int(np.sum(labels == lbl))
        if lbl == -1:
            metrics["cluster_sizes"]["noise"] = count
        else:
            metrics["cluster_sizes"][f"cluster_{lbl}"] = count

    # Silhouette and Davies-Bouldin (need at least 2 clusters and 1 non-noise cluster)
    if n_clusters >= 2 and noise_ratio < 1.0:
        # Exclude noise points for silhouette
        mask = labels != -1
        metrics["silhouette"] = silhouette_score(X[mask], labels[mask])
        metrics["davies_bouldin"] = davies_bouldin_score(X[mask], labels[mask])
    elif n_clusters >= 2:
        metrics["silhouette"] = None
        metrics["davies_bouldin"] = None
    else:
        metrics["silhouette"] = None
        metrics["davies_bouldin"] = None

    return metrics


def label_clusters(X, labels, feature_names):
    """
    Assign human-readable labels to clusters.

    Analyzes cluster characteristics:
    - "Night Jobs": High activity 0-6 AM, batch patterns
    - "OLTP Transactions": High SELECT/INSERT, business hours
    - "Administrators": High DDL, low frequency, many tables
    - "Analytics Users": High aggregation queries, long duration

    Args:
        X (np.ndarray): Feature matrix
        labels (np.ndarray): Cluster assignments
        feature_names (list[str]): Names of features

    Returns:
        dict: {cluster_id: "semantic_label", ...}
    """
    feature_to_idx = {name: i for i, name in enumerate(feature_names)}
    semantic_labels = {}

    unique_labels = np.unique(labels[labels != -1])

    for cluster_id in unique_labels:
        mask = labels == cluster_id
        cluster_center = X[mask].mean(axis=0)

        # Score each heuristic rule
        night_score = 0.0
        oltp_score = 0.0
        admin_score = 0.0
        analytics_score = 0.0

        # Night Jobs: high night hour activity
        for feat in NIGHT_HOUR_FEATURES:
            if feat in feature_to_idx:
                night_score += cluster_center[feature_to_idx[feat]]

        # OLTP: high business hours + high read_ratio
        for feat in BUSINESS_HOUR_FEATURES:
            if feat in feature_to_idx:
                oltp_score += cluster_center[feature_to_idx[feat]]
        if "read_ratio" in feature_to_idx:
            oltp_score += cluster_center[feature_to_idx["read_ratio"]] * 2

        # Administrators: high DDL ratio + many unique tables
        if "ddl_ratio" in feature_to_idx:
            admin_score += cluster_center[feature_to_idx["ddl_ratio"]] * 3
        if "unique_tables" in feature_to_idx:
            admin_score += cluster_center[feature_to_idx["unique_tables"]]

        # Analytics Users: high aggregation ratio + long queries + many joins
        if "has_aggregation_ratio" in feature_to_idx:
            analytics_score += cluster_center[feature_to_idx["has_aggregation_ratio"]] * 2
        if "avg_join_count" in feature_to_idx:
            analytics_score += cluster_center[feature_to_idx["avg_join_count"]] * 2
        if "avg_duration_ms" in feature_to_idx:
            analytics_score += cluster_center[feature_to_idx["avg_duration_ms"]]

        scores = {
            "Night Jobs": night_score,
            "OLTP Transactions": oltp_score,
            "Administrators": admin_score,
            "Analytics Users": analytics_score,
        }

        semantic_labels[int(cluster_id)] = max(scores, key=scores.get)

    # Label noise
    if -1 in np.unique(labels):
        semantic_labels[-1] = "Noise/Outliers"

    return semantic_labels


def plot_clusters_2d(X, labels, semantic_labels=None):
    """
    Visualize clusters in 2D using PCA dimensionality reduction.

    Creates scatter plot:
    - Points colored by cluster assignment
    - Cluster centers marked with stars
    - Optional semantic labels in legend
    - Explained variance ratio in title

    Args:
        X (np.ndarray): Scaled feature matrix
        labels (np.ndarray): Cluster assignments
        semantic_labels (dict, optional): {cluster_id: "label"}

    Returns:
        matplotlib.figure.Figure: Cluster visualization
    """
    n_components = min(2, X.shape[1])
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)

    fig, ax = plt.subplots(figsize=(10, 7))

    unique_labels = np.unique(labels)
    cmap = plt.cm.get_cmap("tab10", len(unique_labels))

    for i, lbl in enumerate(unique_labels):
        mask = labels == lbl
        label_text = semantic_labels.get(lbl, f"Cluster {lbl}") if semantic_labels else f"Cluster {lbl}"
        ax.scatter(
            X_pca[mask, 0], X_pca[mask, 1],
            c=[cmap(i)], label=label_text, s=80, edgecolors="k", alpha=0.7,
        )

        # Mark cluster center
        if lbl != -1:
            center = X_pca[mask].mean(axis=0)
            ax.scatter(center[0], center[1], marker="*", s=300, c=[cmap(i)], edgecolors="k", zorder=10)

    explained = pca.explained_variance_ratio_.sum() * 100
    ax.set_title(f"Cluster Visualization (PCA — {explained:.1f}% variance explained)")
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    ax.legend()
    fig.tight_layout()

    save_path = PROCESSED_DIR / "clusters_2d.png"
    fig.savefig(save_path, dpi=150)
    plt.close(fig)
    print(f"  Cluster plot saved to {save_path}")

    return fig


def plot_cluster_profiles(centers, feature_names, semantic_labels=None):
    """
    Plot cluster profiles as bar charts.

    For each cluster:
    - Shows normalized feature values
    - Highlights distinguishing characteristics
    - Uses semantic labels as titles

    Args:
        centers (np.ndarray): Cluster center coordinates
        feature_names (list[str]): Feature column names
        semantic_labels (dict, optional): {cluster_id: "label"}

    Returns:
        matplotlib.figure.Figure: Profile visualization
    """
    n_clusters = len(centers)
    n_features = len(feature_names)

    # Normalize centers to [0, 1] for comparison
    mins = centers.min(axis=0)
    maxs = centers.max(axis=0)
    ranges = maxs - mins
    ranges[ranges == 0] = 1  # Avoid division by zero
    normalized = (centers - mins) / ranges

    fig, axes = plt.subplots(n_clusters, 1, figsize=(14, 4 * n_clusters))
    if n_clusters == 1:
        axes = [axes]

    for i in range(n_clusters):
        ax = axes[i]
        label = semantic_labels.get(i, f"Cluster {i}") if semantic_labels else f"Cluster {i}"

        y_pos = np.arange(n_features)
        bars = ax.barh(y_pos, normalized[i], color=sns.color_palette("husl", n_clusters)[i])
        ax.set_yticks(y_pos)
        ax.set_yticklabels(feature_names, fontsize=8)
        ax.set_xlabel("Normalized Value (0-1)")
        ax.set_title(f"{label} — Feature Profile")
        ax.set_xlim(0, 1.1)

    fig.suptitle("Cluster Profiles (Normalized Feature Values)", fontsize=14, y=1.01)
    fig.tight_layout()

    save_path = PROCESSED_DIR / "cluster_profiles.png"
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Cluster profiles saved to {save_path}")

    return fig


def run_clustering_analysis(X, feature_names, user_ids=None):
    """
    Execute complete clustering analysis pipeline.

    Pipeline:
    1. Determine optimal number of clusters
    2. Run KMeans clustering
    3. Run DBSCAN clustering
    4. Evaluate both approaches
    5. Assign semantic labels
    6. Generate visualizations
    7. Save results to data/processed/

    Args:
        X (np.ndarray): Scaled feature matrix
        feature_names (list[str]): Feature column names
        user_ids (list[str], optional): User identifiers

    Returns:
        dict: {
            'kmeans_labels': np.ndarray,
            'kmeans_model': KMeans,
            'dbscan_labels': np.ndarray,
            'semantic_labels': dict,
            'metrics': dict,
            'plots': dict
        }
    """
    print("=" * 60)
    print("Clustering Analysis")
    print("=" * 60)
    print(f"  Users: {X.shape[0]}, Features: {X.shape[1]}")

    results = {
        "kmeans_labels": None,
        "kmeans_model": None,
        "dbscan_labels": None,
        "semantic_labels": {},
        "metrics": {},
        "plots": {},
        "user_ids": user_ids,
    }

    # Step 1: Find optimal k
    print("\n[1/6] Finding optimal k (elbow method)...")
    if X.shape[0] >= 3:
        optimal_k, inertias, sil_scores = find_optimal_k(X)
        print(f"  Suggested k = {optimal_k}")
        results["metrics"]["optimal_k"] = optimal_k
    else:
        optimal_k = 2
        print(f"  Too few users ({X.shape[0]}), using k = {optimal_k}")
        results["metrics"]["optimal_k"] = optimal_k

    # Step 2: Run KMeans
    print("\n[2/6] Running KMeans clustering...")
    km_labels, kmeans_model, inertia = run_kmeans(X, n_clusters=optimal_k)
    results["kmeans_labels"] = km_labels
    results["kmeans_model"] = kmeans_model
    results["metrics"]["kmeans_inertia"] = inertia
    print(f"  Inertia: {inertia:.2f}")

    # Evaluate KMeans
    km_metrics = evaluate_clusters(X, km_labels)
    results["metrics"]["kmeans"] = km_metrics
    print(f"  KMeans clusters: {km_metrics['n_clusters']}")
    if km_metrics.get("silhouette") is not None:
        print(f"  Silhouette: {km_metrics['silhouette']:.3f}")
        print(f"  Davies-Bouldin: {km_metrics['davies_bouldin']:.3f}")

    # Step 3: Run DBSCAN
    print("\n[3/6] Running DBSCAN clustering...")
    # Auto-tune eps based on data
    if X.shape[0] >= 5:
        from sklearn.neighbors import NearestNeighbors
        nn = NearestNeighbors(n_neighbors=min(5, X.shape[0]))
        nn.fit(X)
        distances, _ = nn.kneighbors(X)
        eps_estimate = np.sort(distances[:, -1])[int(len(distances) * 0.9)]
        dbscan_eps = max(eps_estimate, 0.1)
    else:
        dbscan_eps = 0.5

    print(f"  DBSCAN eps={dbscan_eps:.3f}, min_samples={min(3, X.shape[0])}")
    db_labels, db_model = run_dbscan(X, eps=dbscan_eps, min_samples=min(3, X.shape[0]))
    results["dbscan_labels"] = db_labels
    results["dbscan_model"] = db_model

    db_metrics = evaluate_clusters(X, db_labels)
    results["metrics"]["dbscan"] = db_metrics
    print(f"  DBSCAN clusters: {db_metrics['n_clusters']}, noise: {db_metrics['noise_ratio']:.1%}")

    # Step 4: Label clusters semantically
    print("\n[4/6] Assigning semantic labels...")
    semantic = label_clusters(X, km_labels, feature_names)
    results["semantic_labels"] = semantic
    for cid, slabel in semantic.items():
        print(f"  Cluster {cid} → {slabel}")

    # Step 5: Generate visualizations
    print("\n[5/6] Generating visualizations...")
    fig_clusters = plot_clusters_2d(X, km_labels, semantic)
    results["plots"]["clusters_2d"] = fig_clusters

    fig_profiles = plot_cluster_profiles(kmeans_model.cluster_centers_, feature_names, semantic)
    results["plots"]["cluster_profiles"] = fig_profiles

    # Step 6: Save summary
    print("\n[6/6] Saving results...")
    summary = {
        "optimal_k": optimal_k,
        "kmeans_inertia": float(inertia),
        "kmeans_metrics": {k: v for k, v in km_metrics.items()},
        "dbscan_metrics": {k: v for k, v in db_metrics.items()},
        "semantic_labels": {str(k): v for k, v in semantic.items()},
    }

    if user_ids is not None:
        user_clusters = pd.DataFrame({
            "username": user_ids,
            "cluster_id": km_labels,
            "cluster_label": [semantic.get(int(l), "Unknown") for l in km_labels],
        })
        csv_path = PROCESSED_DIR / "user_clusters.csv"
        user_clusters.to_csv(csv_path, index=False)
        print(f"  User cluster assignments saved to {csv_path}")

    import json
    json_path = PROCESSED_DIR / "clustering_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary saved to {json_path}")

    print("\n" + "=" * 60)
    print("Clustering Analysis Complete")
    print("=" * 60)

    return results


if __name__ == "__main__":
    from etl.db_client import execute_query
    from feature_eng import prepare_for_clustering

    print("=== Clustering Analysis Runner ===")
    print("Loading data from audit_data.audit_logs...")

    try:
        df = execute_query("SELECT * FROM audit_data.audit_logs")
        if df.empty:
            print("No data found. Run ETL pipeline first.")
        else:
            print(f"Loaded {len(df)} records.")

            n_users = df["username"].nunique()
            print(f"Unique users: {n_users}")

            if n_users < 2:
                print("Not enough users for meaningful clustering (need ≥ 2).")
                print("  Generate more user activity with load_generator.py")
            else:
                # Prepare features
                print("\nPreparing features...")
                X_scaled, user_ids, feature_names, scaler = prepare_for_clustering(df)
                print(f"  Feature matrix: {X_scaled.shape}")

                # Run clustering
                results = run_clustering_analysis(X_scaled, feature_names, user_ids)

                print("\nDone! Check data/processed/ for plots and results.")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
