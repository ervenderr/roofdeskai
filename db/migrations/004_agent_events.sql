-- Append-only audit trail (D-15). No FK to conversations on purpose. A superuser can still disable triggers (Phase 6 non-owner role).
CREATE TABLE IF NOT EXISTS agent_events (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    conversation_id int,
    kind text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS agent_events_tenant_conv_idx ON agent_events (tenant_id, conversation_id, id);

CREATE OR REPLACE FUNCTION agent_events_block() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'agent_events is append-only';
END $$;

DROP TRIGGER IF EXISTS agent_events_no_change ON agent_events;
CREATE TRIGGER agent_events_no_change BEFORE UPDATE OR DELETE ON agent_events
  FOR EACH ROW EXECUTE FUNCTION agent_events_block();
DROP TRIGGER IF EXISTS agent_events_no_truncate ON agent_events;
CREATE TRIGGER agent_events_no_truncate BEFORE TRUNCATE ON agent_events
  FOR EACH STATEMENT EXECUTE FUNCTION agent_events_block();
