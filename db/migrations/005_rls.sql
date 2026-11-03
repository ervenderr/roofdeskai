-- Enforce row-level security: non-owner role app_rw, explicit grants, FORCE RLS, tenant_isolation policies, tenant_id DEFAULTs dropped.
-- The login password is set by bootstrap (set_app_role_login), never in SQL. No default-privilege grants on purpose.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

GRANT USAGE ON SCHEMA public TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON leads, conversations, messages, slots, appointments, faq_chunks,
      tool_calls, escalations, events, llm_calls TO app_rw;
GRANT SELECT, INSERT ON agent_events TO app_rw;  -- append-only

-- Sequences of the granted tables only (never ALL SEQUENCES: keeps tenant_api_keys/outreach ungranted).
DO $$
DECLARE t text; s text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leads','conversations','messages','slots','appointments','faq_chunks',
                           'tool_calls','escalations','events','llm_calls','agent_events'] LOOP
    s := pg_get_serial_sequence(t, 'id');
    IF s IS NOT NULL THEN
      EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO app_rw', s);
    END IF;
  END LOOP;
END $$;

DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leads','conversations','messages','slots','appointments','faq_chunks',
                           'tool_calls','escalations','events','llm_calls','agent_events'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format($p$CREATE POLICY tenant_isolation ON %I
        USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)$p$, t);
  END LOOP;
  FOREACH t IN ARRAY ARRAY['leads','conversations','messages','slots','appointments','faq_chunks',
                           'tool_calls','escalations','events'] LOOP
    EXECUTE format('ALTER TABLE %I ALTER COLUMN tenant_id DROP DEFAULT', t);
  END LOOP;
END $$;
