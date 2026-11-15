CREATE TABLE IF NOT EXISTS jobs (id uuid PRIMARY KEY, profile_id text NOT NULL, status text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), manifest jsonb, artifact jsonb, stale boolean NOT NULL DEFAULT false);
CREATE TABLE IF NOT EXISTS inbox_receipts (event_id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS command_receipts (actor text NOT NULL, command_id uuid NOT NULL, payload_hash text NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(actor,command_id));
CREATE TABLE IF NOT EXISTS source_stream (profile_id text PRIMARY KEY, seq bigint NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (event_id uuid PRIMARY KEY, event jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz, deliveries integer NOT NULL DEFAULT 0);
