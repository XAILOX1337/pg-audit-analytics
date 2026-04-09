# pg-audit-analytics

PostgreSQL audit log analysis tool with machine learning-based anomaly detection.

## Features

- **Automated Log Collection**: PostgreSQL with standard CSV logging (`log_statement = 'all'`)
- **ETL Pipeline**: Parse CSV logs and load into structured database schema
- **Feature Engineering**: Extract meaningful features from audit data
- **Clustering Analysis**: K-Means and DBSCAN for user behavior patterns
- **Anomaly Detection**: Isolation Forest and Local Outlier Factor for identifying suspicious activity
- **Interactive Dashboard**: Jupyter notebook with Plotly visualizations

## Project Structure

```
pg-audit-analytics/
├── sql/                          # Database initialization scripts
│   ├── init_schema.sql           # Full schema + roles + working tables
│   └── pgaudit_setup.sql         # pgAudit configuration helper
├── data/                         # Data storage (in .gitignore)
│   ├── raw_logs/                 # PostgreSQL CSV logs
│   └── processed/                # Processed analysis results
├── etl/                          # Data engineering
│   ├── config.py                 # Database connection configuration
│   ├── db_client.py              # Database connection (SQLAlchemy)
│   ├── parser.py                 # Log parsing logic
│   └── loader.py                 # Data loading to audit_data schema
├── analytics/                    # Data Science
│   ├── feature_eng.py            # Feature preparation
│   ├── clustering.py             # K-Means/DBSCAN models
│   ├── anomaly_detection.py      # Isolation Forest / LOF
│   └── query_analysis.py         # Query performance analysis
├── scripts/                      # Utility scripts
│   ├── load_generator.py         # User activity simulation
│   └── run_pipeline.py           # Full ETL + Analytics pipeline
├── notebooks/                    # Visualization
│   └── analysis_dashboard.ipynb  # Interactive Plotly charts
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
├── SETUP_POSTGRES.md             # Step-by-step PostgreSQL setup for Windows
└── README.md                     # This file
```

## Quick Start

### 1. Prerequisites

- **PostgreSQL 15+** (installed locally, see [SETUP_POSTGRES.md](SETUP_POSTGRES.md))
- Python 3.9+
- pip

### 2. Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Database Connection

```bash
# Copy the environment template
copy .env.example .env

# Edit .env with your PostgreSQL credentials
```

### 4. Initialize Database Schema

```bash
# Run the schema initialization script
psql -U postgres -f sql/init_schema.sql
```

### 5. Configure PostgreSQL Logging

Edit your `postgresql.conf` (located in PostgreSQL data directory) and add:

```conf
log_statement = 'all'
log_duration = on
log_min_duration_statement = 0
log_destination = 'csvlog'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.csv'
log_rotation_age = 1d
```

Restart PostgreSQL after making changes:
```bash
# Services -> PostgreSQL -> Restart
# Or via pgAdmin
```

### 6. Run Analysis

```bash
jupyter notebook notebooks/analysis_dashboard.ipynb
```

## Configuration

### PostgreSQL Settings

Edit `postgresql.conf` (typically at `C:\Program Files\PostgreSQL\16\data\postgresql.conf`) to customize:
- Log retention period
- Audit log level
- CSV log rotation settings

### Environment Variables

Copy `.env.example` to `.env` and set your database connection parameters:

```env
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=your_password
PG_DATABASE=postgres
PG_LOG_PATH=C:\Program Files\PostgreSQL\16\data\log
```

## Architecture

This project works **without Docker**. PostgreSQL runs as a native Windows service:

```
PostgreSQL (Windows Service)
    ├── Standard CSV logging (log_statement = 'all')
    ├── CSV log files → parsed by ETL
    └── audit_data schema → analytics storage

Python (venv)
    ├── ETL pipeline (parse CSV → load to DB)
    ├── Analytics (clustering, anomaly detection)
    └── Dashboard (Jupyter + Plotly)
```

## PostgreSQL Setup (No Docker)

See [SETUP_POSTGRES.md](SETUP_POSTGRES.md) for complete step-by-step instructions:
1. Install PostgreSQL 15+ on Windows
2. Configure CSV logging (`log_statement = 'all'`, `log_destination = 'csvlog'`)
3. Initialize the audit schema
4. Verify the setup
