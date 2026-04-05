# 📋 pg-audit-analytics — Development Plan

## 📊 Project Analysis

The task involves building a complete PostgreSQL audit analytics pipeline with 4 stages:
1. **Infrastructure**: PostgreSQL + pgAudit setup
2. **ETL**: Log parsing and data loading
3. **Analytics**: ML-based clustering & anomaly detection
4. **Visualization**: Interactive dashboard

### Current State
- ✅ Good project structure (matches task requirements)
- ✅ Requirements.txt has all necessary dependencies
- ⚠️ All Python files are empty — need implementation
- ⚠️ Docker configs are empty — need configuration
- ⚠️ No Jupyter notebook content

---

## 🗂️ Updated Project Structure

```
pg-audit-analytics/
├── docker/
│   ├── docker-compose.yml          # PostgreSQL + pgAudit container
│   ├── postgres.conf               # Extended logging + pgAudit config
│   └── init.sql                    # Schema initialization (NEW)
├── data/
│   ├── raw_logs/                   # Raw CSV logs from PostgreSQL
│   └── processed/                  # Processed analysis results
├── etl/
│   ├── db_client.py                # DB connection utilities
│   ├── parser.py                   # CSV log parser
│   ├── loader.py                   # Data loader to audit_data schema
│   └── config.py                   # DB credentials & paths (NEW)
├── analytics/
│   ├── feature_eng.py              # Feature extraction
│   ├── clustering.py               # User clustering (KMeans, DBSCAN)
│   ├── anomaly_detection.py        # Anomaly detection (IsolationForest)
│   └── query_analysis.py           # Query performance analysis (NEW)
├── scripts/
│   ├── load_generator.py           # Simulate DB workload
│   └── run_pipeline.py             # Full ETL + Analytics pipeline (NEW)
├── notebooks/
│   └── analysis_dashboard.ipynb    # Interactive Plotly dashboard
├── requirements.txt
├── .env.example                    # Environment variables template (NEW)
└── README.md
```

---

## 🛠️ Tools & Technologies to Study

### 🔴 MUST STUDY (Core Requirements)

| Tool/Library | Purpose | Priority |
|----------------|----------------------------------------|------------|
| **PostgreSQL** | Core database, schemas, roles, queries |🔥 Critical |
| **pgAudit**    | Audit extension configuration          | 🔥 Critical |
| **Docker & Docker Compose** | Container orchestration   | 🔥 Critical |
| **pandas** | Data manipulation, time series             | 🔥 Critical |
| **SQLAlchemy** | ORM for database operations            | 🔥 Critical |
| **psycopg2** | PostgreSQL adapter for Python            | 🔥 Critical |
| **scikit-learn** | ML models (KMeans, DBSCAN, IsolationForest) | 🔥 Critical |
| **Plotly** | Interactive visualizations | 🔥 Critical |
| **Jupyter Notebook** | Dashboard & analysis environment | 🔥 Critical |

### 🟡 SHOULD KNOW (Important)

| Tool/Library | Purpose |
|-------------|---------|
| **PostgreSQL CSV Log Format** | Understanding log structure |
| **PostgreSQL Roles & Permissions** | Role-based audit filtering |
| **numpy** | Numerical operations |
| **seaborn/matplotlib** | Static visualizations (heatmaps) |
| **python-dotenv** | Environment variable management |
| **datetime/pytz** | Timezone handling for logs |

### 🟢 NICE TO HAVE (Bonus)

| Tool/Library | Purpose |
|-------------|---------|
| **Apache Superset / Redash** | Alternative dashboards |
| **matplotlib** | Additional chart types |
| **joblib/pickle** | Model serialization |
| **logging (Python)** | Script logging |
| **argparse** | CLI arguments |

---

## 📝 Implementation Plan by File

### Phase 1: Infrastructure (Docker + PostgreSQL)

#### `docker/docker-compose.yml`
- PostgreSQL 15+ service with pgAudit extension
- Volume mounts for configs and logs
- Environment variables for credentials
- Port mapping (5432)

#### `docker/postgres.conf`
- `log_statement = 'all'` — log all statements
- `log_duration = on` — log query duration
- `log_rotation_age = 1d` — daily rotation
- `log_filename` — CSV log naming pattern
- `shared_preload_libraries = 'pgaudit'`
- `pgaudit.log = 'ddl,write,role'` — audit DDL + DML + role changes
- `pgaudit.log_level = 'notice'`

#### `docker/init.sql`
- Create `audit_data` schema
- Create normalized tables: `audit_logs`, `query_stats`, `user_activity`
- Create roles: `admin`, `app_user`, `analyst`, `night_job`
- Grant appropriate permissions

---

### Phase 2: ETL Pipeline

#### `etl/config.py`
- Database connection parameters (from env vars)
- File paths for raw/processed data
- Log format constants

#### `etl/db_client.py`
- `create_engine()` — SQLAlchemy engine creation
- `get_connection()` — context manager for connections
- `init_audit_schema()` — create audit_data tables programmatically
- `execute_query()` — generic query executor
- `bulk_insert()` — efficient data loading

#### `etl/parser.py`
- `parse_csv_log_line()` — parse single CSV log line
- `parse_log_file()` — read and parse entire log file
- `extract_fields()` — extract: timestamp, user, operation, table, duration, query
- `clean_data()` — handle NULLs, malformed lines, encoding issues
- `validate_record()` — schema validation

#### `etl/loader.py`
- `load_to_audit_table()` — insert parsed records
- `upsert_record()` — handle duplicates
- `create_indexes()` — optimize query performance
- `run_etl_pipeline()` — orchestrator: parse → clean → load

---

### Phase 3: Analytics

#### `analytics/feature_eng.py`
- `extract_time_features()` — hour_of_day, day_of_week, is_night
- `extract_user_features()` — query_count, avg_duration, operation_distribution
- `extract_query_patterns()` — most_used_tables, operation_types
- `build_feature_matrix()` — combine all features into DataFrame
- `scale_features()` — StandardScaler/MinMaxScaler

#### `analytics/clustering.py`
- `run_kmeans()` — K-Means clustering (find optimal K with elbow method)
- `run_dbscan()` — DBSCAN for density-based clusters
- `evaluate_clusters()` — silhouette score, Davies-Bouldin
- `label_clusters()` — assign semantic labels ("Night Jobs", "OLTP", "Admins")
- `plot_clusters()` — 2D visualization with PCA/t-SNE

#### `analytics/anomaly_detection.py`
- `build_time_series()` — aggregate transactions per minute/hour
- `run_isolation_forest()` — detect outliers
- `run_lof()` — Local Outlier Factor
- `flag_suspicious_activity()` — rule-based + ML hybrid
- `plot_anomalies()` — time series with anomaly markers

#### `analytics/query_analysis.py` (NEW)
- `analyze_query_distribution()` — execution time histograms
- `detect_slow_queries()` — percentile-based thresholds
- `track_query_degradation()` — time-based performance trend
- `identify_index_candidates()` — slow full-table scans
- `plot_query_performance()` — box plots, time series

---

### Phase 4: Visualization

#### `notebooks/analysis_dashboard.ipynb`
- **Section 1**: Data loading & exploration
- **Section 2**: Top-10 most queried tables (bar chart)
- **Section 3**: Operations heatmap by hour (seaborn heatmap)
- **Section 4**: User clustering visualization (scatter with labels)
- **Section 5**: Anomaly timeline (Plotly time series)
- **Section 6**: Query performance distribution (histogram + KDE)
- **Section 7**: Role-based activity breakdown (pie chart)

---

### Utility Scripts

#### `scripts/load_generator.py`
- `simulate_oltp_workload()` — frequent small transactions
- `simulate_admin_queries()` — DDL operations
- `simulate_night_jobs()` — batch processing at night
- `simulate_suspicious_activity()` — unusual patterns for anomaly detection
- `run_load_simulation()` — main orchestrator

#### `scripts/run_pipeline.py` (NEW)
- `run_full_pipeline()` — ETL → Features → Clustering → Anomalies
- CLI interface with argparse

---

## 🚀 Execution Order

1. **Setup Infrastructure** → `docker/` files
2. **Generate Test Data** → `scripts/load_generator.py`
3. **Build ETL** → `etl/` modules
4. **Develop Analytics** → `analytics/` modules
5. **Create Dashboard** → `notebooks/analysis_dashboard.ipynb`
6. **Integration** → `scripts/run_pipeline.py`

---

## 📚 Learning Resources

- **PostgreSQL + pgAudit**: https://github.com/pgaudit/pgaudit
- **pandas time series**: https://pandas.pydata.org/docs/user_guide/timeseries.html
- **scikit-learn clustering**: https://scikit-learn.org/stable/modules/clustering.html
- **Plotly express**: https://plotly.com/python/plotly-express/
- **SQLAlchemy 2.0**: https://docs.sqlalchemy.org/en/20/
