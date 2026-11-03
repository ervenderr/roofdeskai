-- Per-tenant API keys: sha256 hash only. No RLS and no app_rw grant: system context only.
CREATE TABLE IF NOT EXISTS tenant_api_keys (
  id serial PRIMARY KEY,
  tenant_id uuid NOT NULL REFERENCES tenants(id),
  key_hash text NOT NULL UNIQUE,
  label text,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS tenant_api_keys_tenant_idx ON tenant_api_keys (tenant_id);
