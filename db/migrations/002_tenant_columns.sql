-- Add tenant_id to tenant tables. Single-step NOT NULL DEFAULT Summit (PG16 metadata-only); DEFAULT is dropped in Phase 6.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE slots ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE faq_chunks ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE tool_calls ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE escalations ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);
ALTER TABLE events ADD COLUMN IF NOT EXISTS tenant_id uuid NOT NULL DEFAULT '00000000-0000-0000-0000-000000000001' REFERENCES tenants(id);

-- llm_calls also holds outreach rows (no conversation): nullable, no default, so they never get stamped with a tenant.
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES tenants(id);
UPDATE llm_calls l SET tenant_id = c.tenant_id FROM conversations c WHERE l.conversation_id = c.id AND l.tenant_id IS NULL;

CREATE INDEX IF NOT EXISTS faq_chunks_tenant_idx ON faq_chunks (tenant_id);
