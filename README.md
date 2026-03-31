# pg-audit-lens

PostgreSQL audit log analysis tool with machine learning-based anomaly detection.

## Features

- **Automated Log Collection**: PostgreSQL with pgAudit extension for comprehensive audit logging
- **ETL Pipeline**: Parse CSV logs and load into structured database schema
- **Feature Engineering**: Extract meaningful features from audit data
- **Clustering Analysis**: K-Means and DBSCAN for user behavior patterns
- **Anomaly Detection**: Isolation Forest and Local Outlier Factor for identifying suspicious activity
- **Interactive Dashboard**: Jupyter notebook with Plotly visualizations

## Project Structure

```
pg-audit-analytics/
├── docker/                     # Infrastructure configuration
│   ├── postgres.conf           # PostgreSQL and pgAudit settings
│   └── docker-compose.yml      # One-click database setup
├── data/                       # Data storage (in .gitignore)
│   ├── raw_logs/               # PostgreSQL CSV logs
│   └── processed/              # Processed analysis results
├── etl/                        # Data engineering (Phase 2)
│   ├── db_client.py            # Database connection (SQLAlchemy)
│   ├── parser.py               # Log parsing logic
│   └── loader.py               # Data loading to audit_data schema
├── analytics/                  # Data Science (Phase 3)
│   ├── feature_eng.py          # Feature preparation
│   ├── clustering.py           # K-Means/DBSCAN models
│   └── anomaly_detection.py    # Isolation Forest
├── scripts/                    # Utility scripts
│   └── load_generator.py       # User activity simulation
├── notebooks/                  # Visualization (Phase 4)
│   └── analysis_dashboard.ipynb # Interactive Plotly charts
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose
- Python 3.9+
- pip

### 2. Installation

```bash
# Clone the repository
cd pg-audit-analytics

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 3. Start PostgreSQL with pgAudit

```bash
cd docker
docker-compose up -d
```

### 4. Generate Test Data (Optional)

```bash
python scripts/load_generator.py
```

### 5. Run ETL Pipeline

```python
from etl.db_client import DatabaseClient
from etl.parser import LogParser
from etl.loader import DataLoader

# Initialize
db = DatabaseClient()
loader = DataLoader(db)

# Create schema
loader.create_audit_schema()

# Parse and load logs
parser = LogParser('data/raw_logs/your-log-file.csv')
entries = parser.parse_file()
loader.load_entries(entries)
```

### 6. Run Analysis

Open `notebooks/analysis_dashboard.ipynb` in Jupyter:

```bash
jupyter notebook notebooks/analysis_dashboard.ipynb
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=audit_db
DB_USER=admin
DB_PASSWORD=admin123
```

### PostgreSQL Settings

Edit `docker/postgres.conf` to customize:
- Log retention period
- Audit log level
- CSV log rotation settings

## Usage Examples

### Anomaly Detection

```python
from analytics.anomaly_detection import AnomalyDetector
from analytics.feature_eng import FeatureEngineer
import pandas as pd

# Load data
df = pd.read_sql_query("SELECT * FROM audit_data.log_entries", engine)

# Engineer features
fe = FeatureEngineer(df)
fe.extract_time_features()
fe.extract_operation_features()
feature_matrix, feature_names = fe.get_feature_matrix()

# Detect anomalies
detector = AnomalyDetector(feature_matrix, feature_names)
predictions = detector.fit_isolation_forest(contamination=0.05)
anomalies = detector.get_anomalies(predictions)
```

### Clustering

```python
from analytics.clustering import AuditClustering

clustering = AuditClustering(feature_matrix, feature_names)
labels = clustering.fit_kmeans(n_clusters=5)
centers = clustering.get_cluster_centers()
```




