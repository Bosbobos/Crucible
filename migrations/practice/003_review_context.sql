CREATE TABLE review_obligations_projection (
 id uuid PRIMARY KEY, revision integer NOT NULL, doc jsonb NOT NULL
);
CREATE TABLE review_inbox (
 event_id uuid PRIMARY KEY,event_hash text NOT NULL
);
