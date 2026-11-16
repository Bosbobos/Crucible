CREATE TABLE campaign_publications (
 publication_version text PRIMARY KEY, bindings jsonb NOT NULL, sha256 text NOT NULL,
 published_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE active_campaign (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), publication_version text NOT NULL REFERENCES campaign_publications,
 revision integer NOT NULL
);
