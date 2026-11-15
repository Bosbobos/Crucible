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
