-- T2.6 · ClickHouse reverse-lookup schema for encrypted mapping metadata only.
-- No plaintext PHI values are stored here.

CREATE TABLE _phi_lookup
(
  map_id String,                       -- T2.5 map envelope identifier
  change_id LowCardinality(String),    -- SOP change reference
  key_id LowCardinality(String),       -- KeyProvider key alias
  key_generation UInt32,               -- T2.4 generation index
  algorithm LowCardinality(String),     -- 'AES-256-GCM'
  schema_version LowCardinality(String), -- envelope schema version
  nonce_b64 FixedString(16),           -- base64-encoded 96-bit nonce
  aad_sha256 FixedString(64),          -- hex sha256 of canonical AAD
  ciphertext_b64 String,               -- base64-encoded AESGCM ciphertext+tag
  ciphertext_sha256 FixedString(64),   -- hex sha256 of decoded ciphertext (integrity)
  created_at DateTime64(3, 'UTC'),     -- UTC creation timestamp
  retention_until DateTime64(3, 'UTC'), -- HIPAA 6-year retention horizon
  inserted_at DateTime64(3) DEFAULT now64()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(created_at)
ORDER BY (created_at, change_id, map_id)
TTL retention_until + INTERVAL 1 YEAR
SETTINGS index_granularity = 8192;

GRANT INSERT, SELECT ON _phi_lookup TO medharness_desensitize_writer;
REVOKE ALTER UPDATE, ALTER DELETE FROM medharness_desensitize_writer;
