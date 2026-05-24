-- MedHarness T4.1 audit log schema.
-- No plaintext request, response, or PHI values are stored here.

CREATE TABLE _audit_log
(
    event_id UUID,
    timestamp DateTime64(3, 'UTC'),
    actor_agent_role LowCardinality(String),
    actor_model_id String,
    actor_vendor_family LowCardinality(String),
    actor_session_id String,
    action_tool String,
    action_skill Nullable(String),
    action_operation LowCardinality(String),
    context_change_id Nullable(String),
    context_step Nullable(UInt8),
    context_data_levels Array(LowCardinality(String)),
    result_status LowCardinality(String),
    result_reason Nullable(String),
    result_duration_ms Float32,
    input_hash FixedString(64),
    output_hash FixedString(64),
    prev_hash FixedString(64),
    current_hash FixedString(64),
    row_id UInt64,
    inserted_at DateTime64(3) DEFAULT now64()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, row_id)
TTL timestamp + INTERVAL 7 YEAR
SETTINGS index_granularity = 8192;

GRANT INSERT, SELECT ON _audit_log TO medharness_audit_writer;
REVOKE ALTER UPDATE, ALTER DELETE FROM medharness_audit_writer;
