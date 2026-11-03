-- Phase 7 engine tables: drafts queue, capacity flags, daily brief runs, intake people.
-- FINAL when first applied (apply_migrations has no checksum): any fix goes in 008+.
-- Same RLS shape as 005: explicit grants (incl. sequences), ENABLE + FORCE, tenant_isolation policy, no tenant_id DEFAULT.
CREATE TABLE IF NOT EXISTS drafts (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  kind text NOT NULL CHECK (kind IN ('quote','review_reply')),
  status text NOT NULL CHECK (status IN ('pending','approved','rejected','needs_human','sent')),
  payload jsonb NOT NULL DEFAULT '{}',
  input_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS drafts_open_dedupe ON drafts (tenant_id, kind, input_hash)
  WHERE status IN ('pending','needs_human');
CREATE INDEX IF NOT EXISTS drafts_tenant_status_idx ON drafts (tenant_id, status, id);

CREATE TABLE IF NOT EXISTS capacity_flags (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  flag_key text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('over_capacity','understaffed','under_utilised')),
  shift_id text NOT NULL,
  shift_date date NOT NULL,
  input_hash text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}',
  first_flagged_at timestamptz NOT NULL DEFAULT now(),
  reflagged_at timestamptz,
  resolved_at timestamptz,
  UNIQUE (tenant_id, flag_key)
);

CREATE TABLE IF NOT EXISTS brief_runs (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  run_date date NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, run_date)
);

CREATE TABLE IF NOT EXISTS intake_people (
  id bigserial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  person_key text NOT NULL,
  name text,
  waiver_at timestamptz,
  checkin_at timestamptz,
  result jsonb,
  result_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, person_key)
);

DO $$
DECLARE t text; s text;
BEGIN
  FOREACH t IN ARRAY ARRAY['drafts','capacity_flags','brief_runs','intake_people'] LOOP
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON %I TO app_rw', t);
    s := pg_get_serial_sequence(t, 'id');
    IF s IS NOT NULL THEN
      EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO app_rw', s);
    END IF;
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)$p$, t);
  END LOOP;
END $$;

-- intake_people is the only table where rows are removed in tenant context (subject erasure).
GRANT DELETE ON intake_people TO app_rw;
