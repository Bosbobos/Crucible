CREATE TABLE IF NOT EXISTS active_publication (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 release_id text NOT NULL REFERENCES releases(release_id),
 catalog_seq bigint NOT NULL, activated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO active_publication(singleton,release_id,catalog_seq)
 SELECT true,r.release_id,coalesce((SELECT max((event->>'source_seq')::bigint) FROM outbox WHERE event->>'aggregate_id'=r.release_id),0)
 FROM releases r ORDER BY published_at DESC LIMIT 1 ON CONFLICT DO NOTHING;
