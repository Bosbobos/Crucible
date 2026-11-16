CREATE TABLE learning_evidence (
 id text PRIMARY KEY, profile_id text NOT NULL, revision integer NOT NULL, fact_type text NOT NULL,
 fact jsonb NOT NULL, content_publication text NOT NULL
);
CREATE TABLE learning_evidence_revisions (
 id text NOT NULL REFERENCES learning_evidence, revision integer NOT NULL, fact jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(id,revision)
);
