-- Tenants table plus the Summit default tenant (uuid must equal settings.default_tenant_id).
CREATE TABLE IF NOT EXISTS tenants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    slug text UNIQUE NOT NULL,
    name text NOT NULL,
    timezone text NOT NULL,
    pack_slug text,
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO tenants (id, slug, name, timezone, pack_slug)
VALUES ('00000000-0000-0000-0000-000000000001', 'summit-roofing', 'Summit Roofing', 'America/Denver', 'summit-roofing')
ON CONFLICT (id) DO NOTHING;

-- faq_seed.sql inserts explicit ids without advancing the sequence; fix it so per-tenant inserts do not collide.
SELECT setval(pg_get_serial_sequence('faq_chunks', 'id'), (SELECT max(id) FROM faq_chunks))
WHERE EXISTS (SELECT 1 FROM faq_chunks);
