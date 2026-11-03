-- Composite keys. Never auto-dedupes: abort if slots has duplicates.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM slots GROUP BY start_time HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'duplicate slot start_time; resolve before migrating';
  END IF;
END $$;

-- Parent keys so children can reference (tenant_id, id).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['leads', 'conversations', 'slots'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = t || '_tenant_id_id_key') THEN
      EXECUTE 'ALTER TABLE ' || quote_ident(t) || ' ADD CONSTRAINT ' || quote_ident(t || '_tenant_id_id_key') || ' UNIQUE (tenant_id, id)';
    END IF;
  END LOOP;
END $$;

ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_external_id_key;
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_slot_id_key;
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_lead_id_key;
ALTER TABLE conversations ADD CONSTRAINT conversations_tenant_external_key UNIQUE (tenant_id, external_id);
ALTER TABLE slots ADD CONSTRAINT slots_tenant_start_key UNIQUE (tenant_id, start_time);
ALTER TABLE appointments ADD CONSTRAINT appointments_tenant_slot_key UNIQUE (tenant_id, slot_id);
ALTER TABLE appointments ADD CONSTRAINT appointments_tenant_lead_key UNIQUE (tenant_id, lead_id);

-- Single-column FKs become composite (all were plain NO ACTION; kept).
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_lead_id_fkey;
ALTER TABLE conversations ADD CONSTRAINT conversations_lead_id_fkey FOREIGN KEY (tenant_id, lead_id) REFERENCES leads (tenant_id, id);
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_conversation_id_fkey;
ALTER TABLE messages ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id);
ALTER TABLE tool_calls DROP CONSTRAINT IF EXISTS tool_calls_conversation_id_fkey;
ALTER TABLE tool_calls ADD CONSTRAINT tool_calls_conversation_id_fkey FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id);
ALTER TABLE escalations DROP CONSTRAINT IF EXISTS escalations_conversation_id_fkey;
ALTER TABLE escalations ADD CONSTRAINT escalations_conversation_id_fkey FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id);
ALTER TABLE events DROP CONSTRAINT IF EXISTS events_conversation_id_fkey;
ALTER TABLE events ADD CONSTRAINT events_conversation_id_fkey FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id);
ALTER TABLE llm_calls DROP CONSTRAINT IF EXISTS llm_calls_conversation_id_fkey;
ALTER TABLE llm_calls ADD CONSTRAINT llm_calls_conversation_id_fkey FOREIGN KEY (tenant_id, conversation_id) REFERENCES conversations (tenant_id, id);
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_slot_id_fkey;
ALTER TABLE appointments ADD CONSTRAINT appointments_slot_id_fkey FOREIGN KEY (tenant_id, slot_id) REFERENCES slots (tenant_id, id);
ALTER TABLE appointments DROP CONSTRAINT IF EXISTS appointments_lead_id_fkey;
ALTER TABLE appointments ADD CONSTRAINT appointments_lead_id_fkey FOREIGN KEY (tenant_id, lead_id) REFERENCES leads (tenant_id, id);
