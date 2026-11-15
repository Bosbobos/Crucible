CREATE TABLE IF NOT EXISTS releases (
 release_id text PRIMARY KEY, bundle jsonb NOT NULL, published_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS command_receipts (
 actor text NOT NULL, command_id uuid NOT NULL, payload_hash text NOT NULL, response jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(actor, command_id)
);
CREATE TABLE IF NOT EXISTS source_stream (profile_id text PRIMARY KEY, seq bigint NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
 event_id uuid PRIMARY KEY, event jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz, deliveries integer NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS active_publication (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 release_id text NOT NULL REFERENCES releases(release_id),
 catalog_seq bigint NOT NULL, activated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO active_publication(singleton,release_id,catalog_seq)
 SELECT true,r.release_id,coalesce((SELECT max((event->>'source_seq')::bigint) FROM outbox WHERE event->>'aggregate_id'=r.release_id),0)
 FROM releases r ORDER BY published_at DESC LIMIT 1 ON CONFLICT DO NOTHING;
