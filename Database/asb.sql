-- ============================================================
-- SEIP - Service Engineering Intelligence Platform
-- MVP Phase 1
-- Intelligence Layer Schema
--
-- Purpose:
--   Creates the SEIP intelligence layer on top of the existing
--   SEIP_ITSM source tables.
--
-- Source of Truth:
--   Existing ITSM tables remain authoritative for native records.
--
-- SEIP Layer:
--   Evidence -> Correlation -> Activity -> Leakage -> Review
-- ============================================================

BEGIN;

-- ============================================================
-- 1. NORMALIZED EVIDENCE
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,

    -- Source lineage
    source_table VARCHAR(100) NOT NULL,
    source_record_id BIGINT NOT NULL,
    evidence_type VARCHAR(50) NOT NULL,

    -- Operational context
    event_time TIMESTAMPTZ NOT NULL,
    service_name VARCHAR(150),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    pattern_id VARCHAR(80),

    -- Actor / ownership
    actor_id BIGINT REFERENCES seip_users(user_id),
    assignment_group VARCHAR(100),

    -- Evidence content
    title TEXT,
    description TEXT,

    -- Trust / quality
    evidence_confidence NUMERIC(5,2),
    evidence_quality VARCHAR(30) DEFAULT 'VALID',

    -- Audit
    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_seip_evidence_source
        UNIQUE (source_table, source_record_id, evidence_type),

    CONSTRAINT chk_evidence_confidence
        CHECK (
            evidence_confidence IS NULL
            OR (
                evidence_confidence >= 0
                AND evidence_confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_evidence_time
    ON seip_evidence(event_time);

CREATE INDEX IF NOT EXISTS idx_seip_evidence_pattern
    ON seip_evidence(pattern_id);

CREATE INDEX IF NOT EXISTS idx_seip_evidence_service
    ON seip_evidence(service_name);

CREATE INDEX IF NOT EXISTS idx_seip_evidence_ci
    ON seip_evidence(ci_id);

CREATE INDEX IF NOT EXISTS idx_seip_evidence_type
    ON seip_evidence(evidence_type);


-- ============================================================
-- 2. CORRELATION GROUP
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_correlation_group (
    correlation_id BIGSERIAL PRIMARY KEY,

    correlation_key VARCHAR(200) NOT NULL,

    pattern_id VARCHAR(80),
    service_name VARCHAR(150),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),

    first_event_time TIMESTAMPTZ,
    last_event_time TIMESTAMPTZ,

    evidence_count INT DEFAULT 0,

    -- Correlation quality
    correlation_method VARCHAR(50),
    correlation_confidence NUMERIC(5,2),

    -- Lifecycle
    status VARCHAR(30) DEFAULT 'ACTIVE',

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_seip_correlation_key
        UNIQUE (correlation_key),

    CONSTRAINT chk_correlation_confidence
        CHECK (
            correlation_confidence IS NULL
            OR (
                correlation_confidence >= 0
                AND correlation_confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_corr_pattern
    ON seip_correlation_group(pattern_id);

CREATE INDEX IF NOT EXISTS idx_seip_corr_service
    ON seip_correlation_group(service_name);

CREATE INDEX IF NOT EXISTS idx_seip_corr_ci
    ON seip_correlation_group(ci_id);

CREATE INDEX IF NOT EXISTS idx_seip_corr_time
    ON seip_correlation_group(first_event_time, last_event_time);


-- ============================================================
-- 3. CORRELATION ↔ EVIDENCE
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_correlation_evidence (
    correlation_id BIGINT NOT NULL
        REFERENCES seip_correlation_group(correlation_id)
        ON DELETE CASCADE,

    evidence_id BIGINT NOT NULL
        REFERENCES seip_evidence(evidence_id)
        ON DELETE CASCADE,

    relationship_type VARCHAR(50) DEFAULT 'RELATED',

    relationship_confidence NUMERIC(5,2),

    created_at TIMESTAMPTZ DEFAULT now(),

    PRIMARY KEY (correlation_id, evidence_id),

    CONSTRAINT chk_relationship_confidence
        CHECK (
            relationship_confidence IS NULL
            OR (
                relationship_confidence >= 0
                AND relationship_confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_corr_evidence_evidence
    ON seip_correlation_evidence(evidence_id);


-- ============================================================
-- 4. RECONSTRUCTED ENGINEERING ACTIVITY
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_activity (
    activity_id BIGSERIAL PRIMARY KEY,

    correlation_id BIGINT NOT NULL
        REFERENCES seip_correlation_group(correlation_id)
        ON DELETE CASCADE,

    service_name VARCHAR(150),
    ci_id BIGINT REFERENCES cmdb_ci(ci_id),
    pattern_id VARCHAR(80),

    activity_type VARCHAR(80) NOT NULL,

    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ,

    actor_id BIGINT REFERENCES seip_users(user_id),
    assignment_group VARCHAR(100),

    duration_minutes INT,

    evidence_count INT DEFAULT 0,

    -- Initial activity classification
    classification VARCHAR(50),

    classification_reason TEXT,

    classification_confidence NUMERIC(5,2),

    created_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT chk_activity_duration
        CHECK (
            duration_minutes IS NULL
            OR duration_minutes >= 0
        ),

    CONSTRAINT chk_activity_confidence
        CHECK (
            classification_confidence IS NULL
            OR (
                classification_confidence >= 0
                AND classification_confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_activity_corr
    ON seip_activity(correlation_id);

CREATE INDEX IF NOT EXISTS idx_seip_activity_service
    ON seip_activity(service_name);

CREATE INDEX IF NOT EXISTS idx_seip_activity_pattern
    ON seip_activity(pattern_id);

CREATE INDEX IF NOT EXISTS idx_seip_activity_type
    ON seip_activity(activity_type);

CREATE INDEX IF NOT EXISTS idx_seip_activity_classification
    ON seip_activity(classification);


-- ============================================================
-- 5. CAPACITY LEAKAGE
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_capacity_leakage (
    leakage_id BIGSERIAL PRIMARY KEY,

    correlation_id BIGINT NOT NULL
        REFERENCES seip_correlation_group(correlation_id)
        ON DELETE CASCADE,

    service_name VARCHAR(150),
    pattern_id VARCHAR(80),

    leakage_type VARCHAR(50) NOT NULL,

    activity_count INT DEFAULT 0,

    estimated_minutes INT DEFAULT 0,
    estimated_hours NUMERIC(12,2) DEFAULT 0,

    evidence_count INT DEFAULT 0,

    confidence NUMERIC(5,2),

    explanation TEXT,

    -- Current lifecycle
    status VARCHAR(30) DEFAULT 'IDENTIFIED',

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT chk_leakage_minutes
        CHECK (estimated_minutes >= 0),

    CONSTRAINT chk_leakage_hours
        CHECK (estimated_hours >= 0),

    CONSTRAINT chk_leakage_confidence
        CHECK (
            confidence IS NULL
            OR (
                confidence >= 0
                AND confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_leakage_corr
    ON seip_capacity_leakage(correlation_id);

CREATE INDEX IF NOT EXISTS idx_seip_leakage_service
    ON seip_capacity_leakage(service_name);

CREATE INDEX IF NOT EXISTS idx_seip_leakage_pattern
    ON seip_capacity_leakage(pattern_id);

CREATE INDEX IF NOT EXISTS idx_seip_leakage_type
    ON seip_capacity_leakage(leakage_type);

CREATE INDEX IF NOT EXISTS idx_seip_leakage_status
    ON seip_capacity_leakage(status);


-- ============================================================
-- 6. REVIEW QUEUE
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_review_queue (
    review_id BIGSERIAL PRIMARY KEY,

    object_type VARCHAR(50) NOT NULL,
    object_id BIGINT NOT NULL,

    priority VARCHAR(20) DEFAULT 'MEDIUM',

    reason TEXT,

    confidence NUMERIC(5,2),

    status VARCHAR(30) DEFAULT 'PENDING',

    reviewer_id BIGINT REFERENCES seip_users(user_id),

    reviewer_comments TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    reviewed_at TIMESTAMPTZ,

    CONSTRAINT chk_review_confidence
        CHECK (
            confidence IS NULL
            OR (
                confidence >= 0
                AND confidence <= 100
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_seip_review_status
    ON seip_review_queue(status);

CREATE INDEX IF NOT EXISTS idx_seip_review_priority
    ON seip_review_queue(priority);

CREATE INDEX IF NOT EXISTS idx_seip_review_object
    ON seip_review_queue(object_type, object_id);


-- ============================================================
-- 7. QUALITY METRICS
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_quality_metrics (
    metric_id BIGSERIAL PRIMARY KEY,

    metric_time TIMESTAMPTZ DEFAULT now(),

    metric_name VARCHAR(100) NOT NULL,

    metric_value NUMERIC(18,4),

    metric_unit VARCHAR(30),

    scope_type VARCHAR(50),
    scope_value VARCHAR(150),

    status VARCHAR(30),

    details JSONB,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seip_quality_metric
    ON seip_quality_metrics(metric_name);

CREATE INDEX IF NOT EXISTS idx_seip_quality_time
    ON seip_quality_metrics(metric_time);

CREATE INDEX IF NOT EXISTS idx_seip_quality_scope
    ON seip_quality_metrics(scope_type, scope_value);


-- ============================================================
-- 8. DATA PROCESSING RUNS
-- ============================================================
-- Tracks each SEIP intelligence processing execution.
-- This becomes important for freshness, reconciliation,
-- restartability and future incremental processing.

CREATE TABLE IF NOT EXISTS seip_processing_runs (
    run_id BIGSERIAL PRIMARY KEY,

    run_type VARCHAR(50) NOT NULL,

    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,

    status VARCHAR(30) DEFAULT 'RUNNING',

    records_read BIGINT DEFAULT 0,
    records_created BIGINT DEFAULT 0,
    records_updated BIGINT DEFAULT 0,
    records_rejected BIGINT DEFAULT 0,

    error_count INT DEFAULT 0,

    error_message TEXT,

    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_seip_processing_runs_type
    ON seip_processing_runs(run_type);

CREATE INDEX IF NOT EXISTS idx_seip_processing_runs_status
    ON seip_processing_runs(status);

CREATE INDEX IF NOT EXISTS idx_seip_processing_runs_started
    ON seip_processing_runs(started_at);


-- ============================================================
-- 9. SOURCE WATERMARKS
-- ============================================================
-- Supports incremental processing later.
-- We do not need a streaming platform for MVP Phase 1.

CREATE TABLE IF NOT EXISTS seip_source_watermark (
    watermark_id BIGSERIAL PRIMARY KEY,

    source_table VARCHAR(100) NOT NULL,

    timestamp_column VARCHAR(100),

    last_processed_time TIMESTAMPTZ,

    last_processed_id BIGINT,

    records_processed BIGINT DEFAULT 0,

    updated_at TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT uq_seip_source_watermark
        UNIQUE (source_table)
);


-- ============================================================
-- 10. BASIC DATA QUALITY / VALIDATION EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS seip_validation_events (
    validation_id BIGSERIAL PRIMARY KEY,

    run_id BIGINT
        REFERENCES seip_processing_runs(run_id)
        ON DELETE SET NULL,

    validation_type VARCHAR(80) NOT NULL,

    object_type VARCHAR(80),

    object_id BIGINT,

    severity VARCHAR(20) DEFAULT 'INFO',

    validation_status VARCHAR(30) NOT NULL,

    message TEXT,

    details JSONB,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_seip_validation_run
    ON seip_validation_events(run_id);

CREATE INDEX IF NOT EXISTS idx_seip_validation_type
    ON seip_validation_events(validation_type);

CREATE INDEX IF NOT EXISTS idx_seip_validation_status
    ON seip_validation_events(validation_status);


-- ============================================================
-- 11. COMMENTS / DATA DICTIONARY
-- ============================================================

COMMENT ON TABLE seip_evidence IS
'Normalized operational evidence derived from authoritative ITSM source tables.';

COMMENT ON TABLE seip_correlation_group IS
'SEIP reconstructed groups of related operational evidence.';

COMMENT ON TABLE seip_correlation_evidence IS
'Maps normalized evidence records to SEIP correlation groups.';

COMMENT ON TABLE seip_activity IS
'Reconstructed engineering and operational activities derived from correlated evidence.';

COMMENT ON TABLE seip_capacity_leakage IS
'SEIP identification and estimation of engineering capacity leakage.';

COMMENT ON TABLE seip_review_queue IS
'Human governance queue for reviewing SEIP intelligence candidates.';

COMMENT ON TABLE seip_quality_metrics IS
'Operational and intelligence-quality measurements for SEIP.';

COMMENT ON TABLE seip_processing_runs IS
'Execution history for SEIP ingestion and intelligence processing jobs.';

COMMENT ON TABLE seip_source_watermark IS
'Incremental processing state for source tables.';

COMMENT ON TABLE seip_validation_events IS
'Validation and data-quality events generated during SEIP processing.';


COMMIT;