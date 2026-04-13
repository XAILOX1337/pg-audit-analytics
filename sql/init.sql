create table if not exists users (
    id              serial primary key,
    username        varchar(100) not null unique,
    email           varchar(255) not null,
    full_name       varchar(255),
    region          varchar(50) default 'default',
    role            varchar(50) default 'user',
    last_login      timestamptz,
    created_at      timestamptz default now(),
    updated_at      timestamptz default now()
);

create table if not exists customers (
    id              serial primary key,
    name            varchar(255) not null,
    email           varchar(255) not null,
    region          varchar(50),
    phone           varchar(20),
    created_at      timestamptz default now()
);

create table if not exists products (
    id              serial primary key,
    name            varchar(255) not null,
    description     text,
    price           numeric(12, 2) not null check (price >= 0),
    category        varchar(100),
    stock_quantity  integer default 0 check (stock_quantity >= 0),
    created_at      timestamptz default now()
);

create table if not exists orders (
    id              serial primary key,
    customer_id     integer references customers(id) on delete set null,
    product_id      integer references products(id) on delete set null,
    quantity        integer not null default 1 check (quantity > 0),
    total           numeric(12, 2) not null check (total >= 0),
    status          varchar(20) default 'pending'
                        check (status in ('pending', 'processing', 'shipped', 'delivered', 'cancelled')),
    order_date      timestamptz default now(),
    shipped_date    timestamptz,
    created_at      timestamptz default now()
);

create table if not exists logs (
    id              serial primary key,
    timestamp       timestamptz default now(),
    level           varchar(10) default 'info'
                        check (level in ('debug', 'info', 'warning', 'error', 'critical')),
    message         text not null,
    source          varchar(200),
    processed       boolean default false,
    created_at      timestamptz default now()
);

create table if not exists audit_trail (
    id              serial primary key,
    user_id         integer references users(id) on delete set null,
    action          varchar(100) not null,
    target_table    varchar(100),
    target_id       integer,
    old_value       jsonb,
    new_value       jsonb,
    timestamp       timestamptz default now(),
    ip_address      inet
);

create table if not exists analytics (
    id              serial primary key,
    metric_name     varchar(100) not null,
    metric_value    numeric(15, 4),
    dimension       varchar(100),
    recorded_at     timestamptz default now()
);

create table if not exists sessions (
    id              serial primary key,
    user_id         integer references users(id) on delete cascade,
    session_token   varchar(255) not null unique,
    ip_address      inet,
    user_agent      text,
    created_at      timestamptz default now(),
    expires_at      timestamptz not null,
    is_active       boolean default true
);

create table if not exists system_config (
    id              serial primary key,
    config_key      varchar(100) not null unique,
    config_value    jsonb,
    description     text,
    updated_by      varchar(100),
    updated_at      timestamptz default now()
);

create table if not exists temp_data (
    id              serial primary key,
    data            jsonb,
    source          varchar(100),
    created_at      timestamptz default now(),
    processed       boolean default false
);

insert into users (username, email, full_name, region, role) values
    ('alice', 'alice@example.com', 'Alice Johnson', 'us-east', 'admin'),
    ('bob', 'bob@example.com', 'Bob Smith', 'eu-west', 'analyst'),
    ('charlie', 'charlie@example.com', 'Charlie Brown', 'us-west', 'user'),
    ('diana', 'diana@example.com', 'Diana Prince', 'ap-south', 'user'),
    ('etl_service', 'etl@internal.com', 'ETL Service Account', 'internal', 'service')
on conflict (username) do nothing;

insert into customers (name, email, region, phone) values
    ('Acme Corp', 'contact@acme.com', 'us-east', '+1-555-0100'),
    ('Globex Inc', 'info@globex.com', 'eu-west', '+44-20-7946-0958'),
    ('Initech', 'support@initech.com', 'us-west', '+1-555-0200'),
    ('Umbrella Co', 'sales@umbrella.com', 'ap-south', '+81-3-1234-5678'),
    ('Stark Industries', 'tony@stark.com', 'us-east', '+1-555-0300')
on conflict do nothing;

insert into products (name, description, price, category, stock_quantity) values
    ('Widget A', 'Standard widget', 29.99, 'widgets', 1000),
    ('Widget B', 'Premium widget', 49.99, 'widgets', 500),
    ('Gadget X', 'Multi-purpose gadget', 99.99, 'gadgets', 250),
    ('Gadget Y', 'Basic gadget', 59.99, 'gadgets', 750),
    ('Service Plan', 'Annual support plan', 199.99, 'services', 9999)
on conflict do nothing;

insert into orders (customer_id, product_id, quantity, total, status, order_date) values
    (1, 1, 5, 149.95, 'delivered', now() - interval '30 days'),
    (1, 3, 1, 99.99, 'shipped', now() - interval '7 days'),
    (2, 2, 10, 499.90, 'processing', now() - interval '2 days'),
    (3, 5, 1, 199.99, 'pending', now() - interval '1 day'),
    (4, 4, 3, 179.97, 'delivered', now() - interval '45 days'),
    (5, 1, 20, 599.80, 'shipped', now() - interval '3 days'),
    (2, 4, 2, 119.98, 'delivered', now() - interval '60 days'),
    (3, 3, 1, 99.99, 'cancelled', now() - interval '15 days')
on conflict do nothing;

insert into system_config (config_key, config_value, description, updated_by) values
    ('max_connections', '100', 'Maximum database connections', 'admin'),
    ('log_retention_days', '30', 'Days to keep audit logs', 'admin'),
    ('batch_size', '1000', 'Default batch processing size', 'admin'),
    ('maintenance_window', '{"start": "02:00", "end": "04:00"}', 'Scheduled maintenance window', 'admin')
on conflict (config_key) do nothing;

create schema if not exists audit_data;

comment on schema audit_data is
    'Schema for PostgreSQL audit log analytics — parsed logs, aggregations, and ML results';

create table audit_data.audit_logs (
    id                  bigserial primary key,
    timestamp           timestamptz not null,
    username            varchar(100) not null,
    database_name       varchar(100),
    operation_type      varchar(20) not null,
    operation_category  varchar(10) not null,
    table_name          varchar(200),
    duration_ms         numeric(10, 3),
    raw_query           text,
    query_hash          varchar(64),
    session_id          varchar(100),
    application_name    varchar(200),
    created_at          timestamptz default now(),

    constraint chk_audit_logs_operation_type
        check (operation_type in (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE',
            'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
            'GRANT', 'REVOKE'
        )),
    constraint chk_audit_logs_operation_category
        check (operation_category in ('READ', 'WRITE', 'DDL', 'DCL')),
    constraint chk_audit_logs_duration_non_negative
        check (duration_ms is null or duration_ms >= 0)
);

comment on table audit_data.audit_logs is
    'Raw parsed PostgreSQL audit log entries from CSV log files';

comment on column audit_data.audit_logs.query_hash is
    'SHA-256 hash of normalized query for deduplication and pattern matching';

create table audit_data.user_activity (
    id                  bigserial primary key,
    username            varchar(100) not null,
    hour_of_day         smallint not null,
    day_of_week         smallint not null,
    operation_type      varchar(20) not null,
    operation_category  varchar(10) not null,
    query_count         integer not null default 0,
    avg_duration_ms     numeric(10, 3),
    total_duration_ms   numeric(12, 3),
    unique_tables       integer default 0,
    created_at          timestamptz default now(),
    updated_at          timestamptz default now(),

    constraint uq_user_activity
        unique (username, hour_of_day, day_of_week, operation_type),

    constraint chk_user_activity_hour
        check (hour_of_day between 0 and 23),
    constraint chk_user_activity_day
        check (day_of_week between 0 and 6),
    constraint chk_user_activity_count
        check (query_count >= 0),
    constraint chk_user_activity_tables
        check (unique_tables >= 0)
);

comment on table audit_data.user_activity is
    'Aggregated user activity by hour/day/operation — input for clustering';

create table audit_data.query_stats (
    id                  bigserial primary key,
    query_pattern       text not null,
    query_hash          varchar(64) not null unique,
    operation_type      varchar(20) not null,
    table_name          varchar(200),
    execution_count     integer not null default 0,
    avg_duration_ms     numeric(10, 3) not null,
    min_duration_ms     numeric(10, 3),
    max_duration_ms     numeric(10, 3),
    p50_duration_ms     numeric(10, 3),
    p95_duration_ms     numeric(10, 3),
    p99_duration_ms     numeric(10, 3),
    first_seen          timestamptz not null,
    last_seen           timestamptz not null,
    created_at          timestamptz default now(),

    constraint chk_query_stats_count
        check (execution_count >= 0),
    constraint chk_query_stats_avg
        check (avg_duration_ms >= 0)
);

comment on table audit_data.query_stats is
    'Query performance statistics grouped by normalized query pattern';

create table audit_data.anomaly_results (
    id              bigserial primary key,
    timestamp       timestamptz not null,
    anomaly_type    varchar(50) not null,
    severity        varchar(10) not null,
    username        varchar(100),
    description     text,
    metrics         jsonb,
    score           numeric(10, 5),
    created_at      timestamptz default now(),

    constraint chk_anomaly_severity
        check (severity in ('LOW', 'MEDIUM', 'HIGH')),
    constraint chk_anomaly_type
        check (anomaly_type in (
            'isolation_forest', 'lof', 'rule_based',
            'night_spike', 'unusual_access', 'ddl_storm',
            'long_query', 'role_violation'
        ))
);

comment on table audit_data.anomaly_results is
    'Detected anomalies from Isolation Forest, LOF, and rule-based checks';

comment on column audit_data.anomaly_results.metrics is
    'JSONB blob with detailed metrics at time of anomaly detection';

create table audit_data.clustering_results (
    id              bigserial primary key,
    username        varchar(100) not null,
    cluster_id      integer not null,
    cluster_label   varchar(50),
    algorithm       varchar(20) not null,
    features        jsonb,
    created_at      timestamptz default now(),

    constraint chk_clustering_algorithm
        check (algorithm in ('kmeans', 'dbscan')),
    constraint uq_clustering_user_algo
        unique (username, algorithm)
);

comment on table audit_data.clustering_results is
    'User cluster assignments with semantic labels (Night Jobs, OLTP, Admin, etc.)';

comment on column audit_data.clustering_results.features is
    'JSONB feature vector used for clustering (for reproducibility)';

create index if not exists idx_audit_logs_timestamp
    on audit_data.audit_logs (timestamp);

create index if not exists idx_audit_logs_username
    on audit_data.audit_logs (username);

create index if not exists idx_audit_logs_operation_type
    on audit_data.audit_logs (operation_type);

create index if not exists idx_audit_logs_operation_category
    on audit_data.audit_logs (operation_category);

create index if not exists idx_audit_logs_table_name
    on audit_data.audit_logs (table_name);

create index if not exists idx_audit_logs_query_hash
    on audit_data.audit_logs (query_hash);

create index if not exists idx_audit_logs_user_time
    on audit_data.audit_logs (username, timestamp);

create index if not exists idx_user_activity_username
    on audit_data.user_activity (username);

create index if not exists idx_user_activity_hour
    on audit_data.user_activity (hour_of_day);

create index if not exists idx_user_activity_category
    on audit_data.user_activity (operation_category);

create index if not exists idx_user_activity_hour_category
    on audit_data.user_activity (hour_of_day, operation_category);

create index if not exists idx_query_stats_query_hash
    on audit_data.query_stats (query_hash);

create index if not exists idx_query_stats_operation_type
    on audit_data.query_stats (operation_type);

create index if not exists idx_query_stats_table_name
    on audit_data.query_stats (table_name);

create index if not exists idx_query_stats_avg_duration
    on audit_data.query_stats (avg_duration_ms desc);

create index if not exists idx_anomaly_timestamp
    on audit_data.anomaly_results (timestamp);

create index if not exists idx_anomaly_severity
    on audit_data.anomaly_results (severity);

create index if not exists idx_anomaly_username
    on audit_data.anomaly_results (username);

create index if not exists idx_anomaly_time_severity
    on audit_data.anomaly_results (timestamp, severity);

create index if not exists idx_clustering_username
    on audit_data.clustering_results (username);

create index if not exists idx_clustering_algorithm
    on audit_data.clustering_results (algorithm);

create index if not exists idx_clustering_label
    on audit_data.clustering_results (cluster_label);

create or replace view audit_data.user_activity_summary as
select
    username,
    sum(query_count) as total_queries,
    round(avg(avg_duration_ms), 2) as overall_avg_duration_ms,
    sum(total_duration_ms) as total_duration_ms,
    count(distinct hour_of_day) as active_hours_count,
    count(distinct operation_category) as operation_types_used,
    min(hour_of_day) as earliest_active_hour,
    max(hour_of_day) as latest_active_hour
from audit_data.user_activity
group by username;

comment on view audit_data.user_activity_summary is
    'One-row-per-user summary: total queries, avg duration, active hours';

create or replace view audit_data.hourly_activity_heatmap as
select
    hour_of_day,
    operation_category,
    sum(query_count) as total_queries,
    count(distinct username) as active_users,
    round(avg(avg_duration_ms), 2) as avg_duration_ms
from audit_data.user_activity
group by hour_of_day, operation_category
order by hour_of_day, operation_category;

comment on view audit_data.hourly_activity_heatmap is
    'Pre-aggregated data for the operations-by-hour heatmap visualization';

create or replace view audit_data.top_queried_tables as
select
    table_name,
    count(*) as query_count,
    count(distinct username) as unique_users,
    round(avg(duration_ms), 2) as avg_duration_ms,
    max(duration_ms) as max_duration_ms,
    operation_category,
    date_trunc('hour', timestamp) as hour_bucket
from audit_data.audit_logs
where table_name is not null
group by table_name, operation_category, date_trunc('hour', timestamp);

comment on view audit_data.top_queried_tables is
    'Query counts per table per hour — input for top-10 tables chart';

create or replace view audit_data.slow_queries as
select
    al.id,
    al.timestamp,
    al.username,
    al.operation_type,
    al.table_name,
    al.duration_ms,
    al.raw_query,
    qs.p95_duration_ms as p95_threshold,
    round(
        ((al.duration_ms - qs.p95_duration_ms) / nullif(qs.p95_duration_ms, 0)) * 100,
        1
    ) as pct_above_p95
from audit_data.audit_logs al
left join audit_data.query_stats qs on al.query_hash = qs.query_hash
where al.duration_ms is not null
  and (
      qs.p95_duration_ms is not null and al.duration_ms > qs.p95_duration_ms
  )
order by al.duration_ms desc;

comment on view audit_data.slow_queries is
    'Queries exceeding their pattern P95 duration — potential performance issues';

create or replace view audit_data.user_operation_mix as
select
    username,
    operation_category,
    sum(query_count) as total_operations,
    round(
        sum(query_count) * 100.0 / nullif(sum(sum(query_count)) over (partition by username), 0),
        1
    ) as percentage
from audit_data.user_activity
group by username, operation_category;

comment on view audit_data.user_operation_mix is
    'Operation type distribution per user — for stacked bar visualization';

create or replace view audit_data.anomaly_timeline as
select
    date_trunc('hour', timestamp) as hour_bucket,
    count(*) as anomaly_count,
    count(*) filter (where severity = 'HIGH') as high_severity_count,
    count(*) filter (where severity = 'MEDIUM') as medium_severity_count,
    count(*) filter (where severity = 'LOW') as low_severity_count,
    array_agg(distinct anomaly_type) as anomaly_types,
    array_agg(distinct username) filter (where username is not null) as affected_users
from audit_data.anomaly_results
group by date_trunc('hour', timestamp)
order by hour_bucket;

comment on view audit_data.anomaly_timeline is
    'Hourly anomaly counts broken down by severity — for timeline visualization';

create or replace view audit_data.daily_activity as
select
    date(timestamp) as activity_date,
    extract(dow from timestamp)::integer as day_of_week,
    count(*) as total_queries,
    count(distinct username) as unique_users,
    round(avg(duration_ms), 2) as avg_duration_ms,
    count(*) filter (where operation_category = 'DDL') as ddl_count,
    count(*) filter (where operation_category = 'WRITE') as write_count,
    count(*) filter (where operation_category = 'READ') as read_count
from audit_data.audit_logs
group by date(timestamp), extract(dow from timestamp)
order by activity_date;

comment on view audit_data.daily_activity is
    'Daily aggregated metrics — for trend analysis';

-- Generate a normalized hash of a query by replacing literals with placeholders
create or replace function audit_data.compute_query_hash(query_text text)
returns varchar(64)
language sql
immutable
as $func$
    select encode(
        sha256(
            regexp_replace(
                regexp_replace(lower(trim(query_text)), $$'[^'']*'$$, '?', 'g'),
                '\d+',
                '?',
                'g'
            )::bytea
        ),
        'hex'
    );
$func$;

comment on function audit_data.compute_query_hash is
    'Generate a normalized hash of a query by replacing literals with placeholders';

-- Map operation type to category: READ, WRITE, DDL, DCL
create or replace function audit_data.classify_operation(op_type varchar)
returns varchar(10)
language sql
immutable
as $$
    select case op_type
        when 'SELECT' then 'READ'
        when 'INSERT' then 'WRITE'
        when 'UPDATE' then 'WRITE'
        when 'DELETE' then 'WRITE'
        when 'CREATE' then 'DDL'
        when 'ALTER'  then 'DDL'
        when 'DROP'   then 'DDL'
        when 'TRUNCATE' then 'DDL'
        when 'GRANT'  then 'DCL'
        when 'REVOKE' then 'DCL'
        else 'OTHER'
    end;
$$;

comment on function audit_data.classify_operation is
    'Map operation type to category: READ, WRITE, DDL, DCL';

-- Rebuild user_activity table from audit_logs — safe to run repeatedly (upsert)
create or replace function audit_data.refresh_user_activity()
returns void
language plpgsql
as $$
begin
    insert into audit_data.user_activity (
        username, hour_of_day, day_of_week,
        operation_type, operation_category,
        query_count, avg_duration_ms, total_duration_ms, unique_tables
    )
    select
        username,
        extract(hour from timestamp)::smallint as hour_of_day,
        extract(dow from timestamp)::smallint as day_of_week,
        operation_type,
        operation_category,
        count(*) as query_count,
        round(avg(duration_ms), 3) as avg_duration_ms,
        round(sum(duration_ms), 3) as total_duration_ms,
        count(distinct table_name) as unique_tables
    from audit_data.audit_logs
    group by
        username,
        extract(hour from timestamp),
        extract(dow from timestamp),
        operation_type,
        operation_category
    on conflict (username, hour_of_day, day_of_week, operation_type)
    do update set
        query_count = excluded.query_count,
        avg_duration_ms = excluded.avg_duration_ms,
        total_duration_ms = excluded.total_duration_ms,
        unique_tables = excluded.unique_tables,
        updated_at = now();
end;
$$;

comment on function audit_data.refresh_user_activity is
    'Rebuild user_activity table from audit_logs — safe to run repeatedly (upsert)';

do $$
begin
    if not exists (select from pg_roles where rolname = 'admin') then
        create role admin with login password 'admin_password' superuser;
    end if;

    if not exists (select from pg_roles where rolname = 'app_user') then
        create role app_user with login password 'app_password' nosuperuser;
    end if;

    if not exists (select from pg_roles where rolname = 'analyst') then
        create role analyst with login password 'analyst_password' nosuperuser;
    end if;

    if not exists (select from pg_roles where rolname = 'night_job') then
        create role night_job with login password 'night_password' nosuperuser;
    end if;
end
$$;

grant usage on schema audit_data to app_user, analyst, night_job;
grant all on schema audit_data to admin;

grant select, insert, update, delete on all tables in schema public to app_user;
grant select on all tables in schema public to analyst;
grant select, insert, update, delete on all tables in schema public to night_job;
grant all on all tables in schema public to admin;

grant usage, select on all sequences in schema public to app_user;
grant usage, select on all sequences in schema public to night_job;
grant all on all sequences in schema public to admin;

grant select on all tables in schema audit_data to analyst;

grant select, insert, update on all tables in schema audit_data to app_user;
grant usage, select on all sequences in schema audit_data to app_user;

grant select, insert, update on all tables in schema audit_data to night_job;
grant usage, select on all sequences in schema audit_data to night_job;

grant all on all tables in schema audit_data to admin;
grant all on all sequences in schema audit_data to admin;

grant execute on all functions in schema audit_data to analyst;
grant execute on all functions in schema audit_data to app_user;
grant execute on all functions in schema audit_data to night_job;

alter default privileges in schema audit_data
    grant select on tables to analyst;

alter default privileges in schema audit_data
    grant select, insert, update on tables to app_user, night_job;

alter default privileges in schema audit_data
    grant all on tables to admin;

do $$
declare
    table_count integer;
    view_count integer;
    index_count integer;
    role_count integer;
begin
    select count(*) into table_count
    from information_schema.tables
    where table_schema = 'audit_data' and table_type = 'BASE TABLE';

    select count(*) into view_count
    from information_schema.views
    where table_schema = 'audit_data';

    select count(*) into index_count
    from pg_indexes
    where schemaname = 'audit_data';

    select count(*) into role_count
    from pg_roles
    where rolname in ('admin', 'app_user', 'analyst', 'night_job');

    raise notice '============================================';
    raise notice ' pg-audit-analytics: Database Initialized';
    raise notice '============================================';
    raise notice ' Working tables (public): 9 (users, orders, products, etc.)';
    raise notice ' Audit tables: %', table_count;
    raise notice ' Views: %', view_count;
    raise notice ' Indexes: %', index_count;
    raise notice ' Roles configured: %', role_count;
    raise notice '============================================';
    raise notice ' Ready for load generation and ETL pipeline';
    raise notice '============================================';
end
$$;
