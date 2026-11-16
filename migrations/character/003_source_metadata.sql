CREATE TABLE campaign_projection (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), source_seq bigint NOT NULL,
 publication_version text NOT NULL, bindings jsonb NOT NULL
);
CREATE TABLE campaign_publications (
 publication_version text PRIMARY KEY, sha256 text NOT NULL, bindings jsonb NOT NULL,
 received_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER campaign_immutable BEFORE UPDATE OR DELETE ON campaign_publications
 FOR EACH ROW EXECUTE FUNCTION reject_immutable_update();
CREATE TABLE profile_settings_projection (
 profile_id text PRIMARY KEY, revision integer NOT NULL, timezone text NOT NULL
);
CREATE TABLE source_checkpoints (source text PRIMARY KEY,applied_seq bigint NOT NULL);
