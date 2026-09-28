
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS seip_users (
    user_id BIGSERIAL PRIMARY KEY,
    user_name VARCHAR(100) NOT NULL,
    email VARCHAR(180) UNIQUE NOT NULL,
    department VARCHAR(100),
    location VARCHAR(100),
    role VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cmdb_ci (
    ci_id BIGSERIAL PRIMARY KEY,
    ci_name VARCHAR(180) UNIQUE NOT NULL,
    ci_type VARCHAR(80) NOT NULL,
    environment VARCHAR(30) NOT NULL,
    os_platform VARCHAR(80),
    application_name VARCHAR(120),
    service_name VARCHAR(120),
    ip_address INET,
    status VARCHAR(30) DEFAULT 'Active',
    criticality VARCHAR(20) DEFAULT 'Medium',
    owner_group VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS problem_records (
    problem_id BIGSERIAL PRIMARY KEY,
    problem_number VARCHAR(30) UNIQUE NOT NULL,
    short_description TEXT NOT NULL,
    category VARCHAR(50),
    subcategory VARCHAR(80),
    root_cause TEXT,
    known_error BOOLEAN DEFAULT FALSE,
    workaround TEXT,
    status VARCHAR(30),
    priority VARCHAR(20),
    assignment_group VARCHAR(100),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    first_detected_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runbooks (
    runbook_id BIGSERIAL PRIMARY KEY,
    runbook_number VARCHAR(30) UNIQUE NOT NULL,
    title VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    technology VARCHAR(80),
    trigger_signature TEXT,
    purpose TEXT,
    steps JSONB NOT NULL,
    rollback_steps JSONB,
    estimated_minutes INT,
    automation_level VARCHAR(30),
    owner_group VARCHAR(100),
    success_rate NUMERIC(5,2),
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id BIGSERIAL PRIMARY KEY,
    incident_number VARCHAR(30) UNIQUE NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    caller_id BIGINT REFERENCES seip_users(user_id),
    category VARCHAR(50),
    subcategory VARCHAR(100),
    service VARCHAR(150),
    short_description TEXT NOT NULL,
    description TEXT,
    impact INT,
    urgency INT,
    priority VARCHAR(20),
    state VARCHAR(30),
    assignment_group VARCHAR(100),
    assigned_to BIGINT REFERENCES seip_users(user_id),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    problem_id BIGINT REFERENCES problem_records(problem_id),
    runbook_id BIGINT REFERENCES runbooks(runbook_id),
    parent_incident_id BIGINT REFERENCES incidents(incident_id),
    source VARCHAR(50),
    symptom_signature VARCHAR(200),
    normalized_pattern_id VARCHAR(80),
    ai_candidate BOOLEAN DEFAULT FALSE,
    ai_confidence NUMERIC(5,2),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id BIGSERIAL PRIMARY KEY,
    alert_number VARCHAR(40) UNIQUE NOT NULL,
    alert_time TIMESTAMPTZ NOT NULL,
    source VARCHAR(80),
    monitoring_tool VARCHAR(100),
    alert_type VARCHAR(100),
    severity VARCHAR(20),
    metric_name VARCHAR(120),
    metric_value NUMERIC,
    threshold_value NUMERIC,
    message TEXT,
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    incident_id BIGINT REFERENCES incidents(incident_id),
    normalized_pattern_id VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS changes (
    change_id BIGSERIAL PRIMARY KEY,
    change_number VARCHAR(30) UNIQUE NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    planned_start TIMESTAMPTZ,
    planned_end TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    change_type VARCHAR(40),
    risk VARCHAR(20),
    impact VARCHAR(20),
    state VARCHAR(40),
    short_description TEXT NOT NULL,
    implementation_plan TEXT,
    backout_plan TEXT,
    assignment_group VARCHAR(100),
    requested_by BIGINT REFERENCES seip_users(user_id),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    related_problem_id BIGINT REFERENCES problem_records(problem_id),
    normalized_pattern_id VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS change_tasks (
    change_task_id BIGSERIAL PRIMARY KEY,
    task_number VARCHAR(40) UNIQUE NOT NULL,
    change_id BIGINT NOT NULL REFERENCES changes(change_id) ON DELETE CASCADE,
    task_type VARCHAR(60),
    sequence_no INT,
    short_description TEXT NOT NULL,
    assignment_group VARCHAR(100),
    assigned_to BIGINT REFERENCES seip_users(user_id),
    state VARCHAR(30),
    planned_start TIMESTAMPTZ,
    planned_end TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    task_result TEXT,
    normalized_pattern_id VARCHAR(80)
);

CREATE TABLE IF NOT EXISTS approval_history (
    approval_id BIGSERIAL PRIMARY KEY,
    approval_number VARCHAR(40) UNIQUE NOT NULL,
    object_type VARCHAR(30) NOT NULL,
    object_id BIGINT NOT NULL,
    approver_id BIGINT REFERENCES seip_users(user_id),
    approval_level INT,
    state VARCHAR(30),
    comments TEXT,
    requested_at TIMESTAMPTZ,
    decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS resolver_history (
    history_id BIGSERIAL PRIMARY KEY,
    incident_id BIGINT REFERENCES incidents(incident_id) ON DELETE CASCADE,
    change_task_id BIGINT REFERENCES change_tasks(change_task_id) ON DELETE CASCADE,
    event_time TIMESTAMPTZ NOT NULL,
    resolver_id BIGINT REFERENCES seip_users(user_id),
    action_type VARCHAR(80),
    action_details TEXT,
    evidence TEXT,
    result VARCHAR(80),
    next_action TEXT,
    duration_minutes INT,
    normalized_pattern_id VARCHAR(80)
);

CREATE INDEX IF NOT EXISTS idx_incidents_pattern ON incidents(normalized_pattern_id);
CREATE INDEX IF NOT EXISTS idx_incidents_opened ON incidents(opened_at);
CREATE INDEX IF NOT EXISTS idx_incidents_ci ON incidents(ci_id);
CREATE INDEX IF NOT EXISTS idx_alerts_pattern ON alerts(normalized_pattern_id);
CREATE INDEX IF NOT EXISTS idx_changes_pattern ON changes(normalized_pattern_id);
CREATE INDEX IF NOT EXISTS idx_tasks_pattern ON change_tasks(normalized_pattern_id);
CREATE INDEX IF NOT EXISTS idx_resolver_pattern ON resolver_history(normalized_pattern_id);
