CREATE TABLE IF NOT EXISTS attempt_facts_projection (attempt_id uuid PRIMARY KEY, revision integer NOT NULL, fact jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS catalog_projection (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), source_seq bigint NOT NULL, release_id text NOT NULL, catalog jsonb NOT NULL);
CREATE TABLE IF NOT EXISTS source_cursors (source text PRIMARY KEY, seq bigint NOT NULL DEFAULT 0);
INSERT INTO source_cursors(source,seq) VALUES ('practice',0),('content',0) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS inbox_receipts (event_id uuid PRIMARY KEY, source text NOT NULL, source_seq bigint NOT NULL, event_hash text NOT NULL, UNIQUE(source,source_seq));
CREATE TABLE IF NOT EXISTS settings (profile_id text PRIMARY KEY, revision integer NOT NULL, timezone text NOT NULL, daily_count integer NOT NULL, weights jsonb NOT NULL DEFAULT '{}');
INSERT INTO settings VALUES ('owner',1,'Europe/Moscow',3,'{}') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS daily_plans (id uuid PRIMARY KEY, profile_id text NOT NULL, study_date date NOT NULL, revision integer NOT NULL, plan jsonb NOT NULL, UNIQUE(profile_id,study_date));
CREATE TABLE IF NOT EXISTS plan_drafts (id uuid PRIMARY KEY, title text NOT NULL);
CREATE TABLE IF NOT EXISTS command_receipts (actor text NOT NULL, command_id uuid NOT NULL, payload_hash text NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(actor,command_id));
CREATE TABLE IF NOT EXISTS source_stream (profile_id text PRIMARY KEY, seq bigint NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (event_id uuid PRIMARY KEY, event jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz, deliveries integer NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS daily_plan_revisions (
 plan_id uuid NOT NULL, revision integer NOT NULL, plan jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(plan_id,revision)
);
INSERT INTO daily_plan_revisions(plan_id,revision,plan)
 SELECT id,revision,plan FROM daily_plans ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS settings_revisions (
 profile_id text NOT NULL, revision integer NOT NULL, settings jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(profile_id,revision)
);
INSERT INTO settings_revisions(profile_id,revision,settings)
 SELECT profile_id,revision,to_jsonb(settings) FROM settings ON CONFLICT DO NOTHING;
