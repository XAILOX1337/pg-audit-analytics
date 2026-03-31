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


### 4. Run Analysis

Open `notebooks/analysis_dashboard.ipynb` in Jupyter:

```bash
jupyter notebook notebooks/analysis_dashboard.ipynb
```


### PostgreSQL Settings

Edit `docker/postgres.conf` to customize:
- Log retention period
- Audit log level
- CSV log rotation settings





