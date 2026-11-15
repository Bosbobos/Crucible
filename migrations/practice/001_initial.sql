CREATE TABLE IF NOT EXISTS attempts (
 id uuid PRIMARY KEY, profile_id text NOT NULL, revision integer NOT NULL,
 state text NOT NULL CHECK(state IN ('running','paused','completed','abandoned')), doc jsonb NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_attempt ON attempts(profile_id) WHERE state IN ('running','paused');
CREATE TABLE IF NOT EXISTS attempt_revisions (
 attempt_id uuid REFERENCES attempts(id), revision integer NOT NULL, doc jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(attempt_id,revision)
);
CREATE TABLE IF NOT EXISTS questions (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES attempts(id), revision integer NOT NULL DEFAULT 1,
 text text NOT NULL, status text NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS reviews (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES attempts(id), attempt_revision integer NOT NULL,
 actor text NOT NULL, text text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS correction_proposals (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES attempts(id), expected_revision integer NOT NULL,
 outcome text NOT NULL, reason text NOT NULL, status text NOT NULL DEFAULT 'pending'
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash text PRIMARY KEY, csrf text NOT NULL, expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS login_limits (bucket text PRIMARY KEY, started_at timestamptz NOT NULL, attempts integer NOT NULL);
CREATE TABLE IF NOT EXISTS command_receipts (
 actor text NOT NULL, command_id uuid NOT NULL, payload_hash text NOT NULL, response jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(actor,command_id)
);
CREATE TABLE IF NOT EXISTS source_stream (profile_id text PRIMARY KEY, seq bigint NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
 event_id uuid PRIMARY KEY, event jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz, deliveries integer NOT NULL DEFAULT 0
);
