CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ds_reference (
  id         BIGSERIAL PRIMARY KEY,
  type       VARCHAR(50)  NOT NULL,
  name       VARCHAR(255) NOT NULL,
  content    TEXT         NOT NULL,
  metadata   JSONB        DEFAULT '{}',
  embedding  vector(1536),
  created_at TIMESTAMPTZ  DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ds_decisions (
  id           BIGSERIAL PRIMARY KEY,
  adr_number   INTEGER      NOT NULL UNIQUE,
  title        VARCHAR(255) NOT NULL,
  status       VARCHAR(50)  DEFAULT 'accepted',
  context      TEXT         NOT NULL,
  decision     TEXT         NOT NULL,
  rationale    TEXT         NOT NULL,
  alternatives TEXT,
  embedding    vector(1536),
  created_at   TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ref_embedding
  ON ds_reference USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_dec_embedding
  ON ds_decisions USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_ref_type ON ds_reference (type);
CREATE INDEX IF NOT EXISTS idx_dec_status ON ds_decisions (status);
