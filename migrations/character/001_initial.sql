CREATE TABLE definition_publications (
 version text PRIMARY KEY, sha256 text NOT NULL UNIQUE, definitions jsonb NOT NULL,
 published_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE character_profile (
 profile_id text PRIMARY KEY, revision integer NOT NULL DEFAULT 1,
 summary jsonb NOT NULL, computed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE inbox_events (
 producer text NOT NULL, event_id uuid NOT NULL, event_hash text NOT NULL,
 source_seq bigint NOT NULL, correlation_id uuid NOT NULL, disposition text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(producer,event_id)
);
CREATE TABLE source_facts (
 profile_id text NOT NULL, producer text NOT NULL, fact_type text NOT NULL, fact_id text NOT NULL,
 revision integer NOT NULL, fact_hash text NOT NULL, fact jsonb NOT NULL,
 PRIMARY KEY(profile_id,producer,fact_type,fact_id)
);
CREATE TABLE fact_revisions (
 profile_id text NOT NULL, producer text NOT NULL, fact_type text NOT NULL, fact_id text NOT NULL,
 revision integer NOT NULL, fact jsonb NOT NULL, event_id uuid NOT NULL,
 PRIMARY KEY(profile_id,producer,fact_type,fact_id,revision)
);
CREATE TABLE xp_entitlements (
 profile_id text NOT NULL, business_key text NOT NULL, amount integer NOT NULL CHECK(amount>=0),
 evidence jsonb NOT NULL, PRIMARY KEY(profile_id,business_key)
);
CREATE TABLE xp_ledger (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, profile_id text NOT NULL,
 business_key text NOT NULL, delta integer NOT NULL CHECK(delta<>0),
 summary_revision integer NOT NULL, event_id uuid NOT NULL, source_revision integer NOT NULL,
 correlation_id uuid NOT NULL, ruleset text NOT NULL, evidence jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(profile_id,business_key,summary_revision)
);
CREATE TABLE seal_state (
 profile_id text NOT NULL, seal_id text NOT NULL, state jsonb NOT NULL,
 ever_granted boolean NOT NULL DEFAULT false, PRIMARY KEY(profile_id,seal_id)
);
CREATE TABLE item_ownership (
 profile_id text NOT NULL, item_id text NOT NULL, ever_granted boolean NOT NULL DEFAULT true,
 current_qualified boolean NOT NULL, evidence_recheck boolean NOT NULL DEFAULT false,
 granted_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(profile_id,item_id)
);
CREATE TABLE loadouts (
 profile_id text PRIMARY KEY, revision integer NOT NULL DEFAULT 1, slots jsonb NOT NULL
);
CREATE TABLE collection_placements (
 profile_id text PRIMARY KEY, revision integer NOT NULL DEFAULT 1, positions jsonb NOT NULL
);
CREATE TABLE preferences (
 profile_id text PRIMARY KEY, revision integer NOT NULL DEFAULT 1, preferences jsonb NOT NULL
);
CREATE TABLE reward_journal (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, profile_id text NOT NULL,
 correlation_id uuid NOT NULL, summary_revision integer NOT NULL, delta integer NOT NULL,
 items jsonb NOT NULL, silent boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(profile_id,summary_revision)
);
CREATE TABLE operations (
 profile_id text NOT NULL, correlation_id uuid NOT NULL, result jsonb NOT NULL,
 PRIMARY KEY(profile_id,correlation_id)
);
CREATE TABLE command_receipts (
 actor text NOT NULL, command_id uuid NOT NULL, payload_hash text NOT NULL, response jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(actor,command_id)
);
CREATE TABLE source_stream (profile_id text PRIMARY KEY, seq bigint NOT NULL);
CREATE TABLE outbox (
 event_id uuid PRIMARY KEY, event jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz, deliveries integer NOT NULL DEFAULT 0
);
CREATE INDEX pending_outbox ON outbox(created_at) WHERE published_at IS NULL;
CREATE INDEX journal_profile_cursor ON reward_journal(profile_id,id);
CREATE INDEX inbox_source_sequence ON inbox_events(producer,source_seq);
