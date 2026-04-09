# PostgreSQL Setup Guide for Windows (No Docker)

This guide walks you through installing and configuring PostgreSQL on Windows — **no Docker, no pgAudit required**.

The project uses **standard PostgreSQL CSV logging** (`log_statement = 'all'`) — no extensions needed.

---

## Table of Contents

1. [Install PostgreSQL](#1-install-postgresql)
2. [Configure PostgreSQL for Audit Logging](#2-configure-postgresql-for-audit-logging)
3. [Initialize the Database Schema](#3-initialize-the-database-schema)
4. [Verify the Setup](#4-verify-the-setup)
5. [Troubleshooting](#troubleshooting)

---

## 1. Install PostgreSQL

### Download

1. Go to: https://www.postgresql.org/download/windows/
2. Download the **EnterpriseDB installer** (recommended)
3. Choose version **15** or **16** (both work with this project)

### Install

1. Run the installer as Administrator
2. Accept default installation path (e.g., `C:\Program Files\PostgreSQL\16`)
3. Set a password for the `postgres` superuser — **remember this!**
4. Keep default port: `5432`
5. Keep default locale
6. Let Stack Builder run (you can skip it — we don't need additional components)

### Verify Installation

Open **Command Prompt** and run:

```cmd
psql -U postgres -c "SELECT version();"
```

You should see PostgreSQL version output. If it asks for a password, enter the one you set during installation.

---

## 2. Configure PostgreSQL for Audit Logging

### Find `postgresql.conf`

The configuration file is located at:

```
C:\Program Files\PostgreSQL\16\data\postgresql.conf
```

(Adjust `16` to your version number)

### Edit `postgresql.conf`

Open the file in a text editor **as Administrator** and add/modify these settings:

```conf
# ============================================================
# pg-audit-analytics Configuration
# Uses standard PostgreSQL logging
# ============================================================

# --- Statement logging (captures ALL SQL) ---
log_statement = 'all'
log_duration = on
log_min_duration_statement = 0

# --- CSV log output ---
log_destination = 'csvlog'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.csv'
log_rotation_age = 1d
log_rotation_size = 100MB
log_truncate_on_rotation = on

# --- Log prefix (useful for parsing) ---
log_line_prefix = '%m [%p] %u@%d '
log_timezone = 'UTC'
log_connections = on
log_disconnections = on
log_lock_waits = on
```

> **Note:** This project does **NOT** require `shared_preload_libraries` or pgAudit. Standard statement logging is sufficient.

### Restart PostgreSQL

After saving the config file, restart the service:

**Method 1 — Services:**
1. Press `Win + R` → type `services.msc` → Enter
2. Find **postgresql-x64-16** (or your version)
3. Right-click → **Restart**

**Method 2 — Command line (as Administrator):**

```cmd
net stop postgresql-x64-18
net start postgresql-x64-18
```

### Verify Logging is Working

Run a test query:

```cmd
psql -U postgres -c "SELECT 1 AS test;"
```

Check if CSV logs are created:

```cmd
dir "C:\Program Files\PostgreSQL\16\data\log\*.csv"
```

You should see at least one CSV file. Open it — you'll see rows like:

```csv
2024-04-06 12:00:00.000 UTC,"postgres","postgres",1234,"[local]",...,"SELECT",...,"statement: SELECT 1 AS test;",...
```

The `command_tag` column (column 8) shows `SELECT`, `INSERT`, `UPDATE`, etc. — this is what the parser reads.

---

## 4. Initialize the Database Schema

### Navigate to the project directory

```cmd
cd O:\pg-audit-analytics
```

### Create virtual environment and install dependencies

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Configure `.env` file

```cmd
copy .env.example .env
```

Edit `.env` with your PostgreSQL password:

```env
PG_HOST=localhost
PG_PORT=5432
PG_USER=postgres
PG_PASSWORD=your_actual_password
PG_DATABASE=postgres
PG_LOG_PATH=C:\Program Files\PostgreSQL\16\data\log
```

### Run the schema initialization script

```cmd
psql -U postgres -f sql\init_schema.sql
```

You should see output like:

```
NOTICE:  ============================================
NOTICE:   pg-audit-analytics: Database Initialized
NOTICE:  ============================================
NOTICE:   Working tables (public): 9
NOTICE:   Audit tables: 5
NOTICE:   Views: 7
NOTICE:   Indexes: 25
NOTICE:   Roles configured: 4
NOTICE:  ============================================
```

---

## 5. Verify the Setup

### Test database connection from Python

```cmd
python -c "from etl.db_client import list_audit_tables; print(list_audit_tables())"
```

You should see a list of audit_data tables.

### Test the ETL pipeline

```cmd
python -m etl.loader
```

This will attempt to parse CSV logs and load them into the database. If no audit logs exist yet, it will report "No data parsed" — this is normal.

### Generate test workload (optional)

If you have `scripts/load_generator.py` implemented, run it to generate test data that will be captured by pgAudit.

---

## 6. Troubleshooting

### `psql: command not found`

PostgreSQL's `bin` directory is not in your PATH. Add it:

1. Open **System Properties** → **Environment Variables**
2. Edit **Path** variable
3. Add: `C:\Program Files\PostgreSQL\16\bin` (adjust version)

Or use the full path:

```cmd
"C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres
```

### `could not open extension control file "pgaudit.control"`

pgAudit is not installed correctly. Revisit [Step 2](#2-install-pgaudit-extension).

### `FATAL: role "postgres" does not exist`

Your superuser might have a different name. Check during installation what username you set.

### CSV log files are not created

1. Verify `log_destination = 'csvlog'` in postgresql.conf
2. Verify `logging_collector = on`
3. Check the log directory exists: `C:\Program Files\PostgreSQL\16\data\log`
4. Restart PostgreSQL after making changes

### Permission denied when running init_schema.sql

Make sure you're connecting as a superuser:

```cmd
psql -U postgres -f sql\init_schema.sql
```

If `postgres` is not your superuser, use the correct username.

### Connection refused

1. Verify PostgreSQL is running: `netstat -an | findstr 5432`
2. Check `postgresql.conf`: `listen_addresses = '*'`
3. Check `pg_hba.conf` allows local connections:
   ```
   host    all    all    127.0.0.1/32    md5
   host    all    all    ::1/128         md5
   ```

---

## Next Steps

After successful setup:

1. **Generate test workload** → run `scripts/load_generator.py`
2. **Run ETL pipeline** → `python -m etl.loader`
3. **Open Jupyter dashboard** → `jupyter notebook notebooks/analysis_dashboard.ipynb`
