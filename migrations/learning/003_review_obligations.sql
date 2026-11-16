CREATE TABLE review_obligations (
 id uuid PRIMARY KEY,profile_id text NOT NULL,problem_id text NOT NULL,
 content_release_id text NOT NULL,plan_id uuid NOT NULL,plan_revision integer NOT NULL,
 due_at timestamptz NOT NULL,last_credited_learning_at timestamptz NOT NULL,
 UNIQUE(plan_id,plan_revision,problem_id)
);
