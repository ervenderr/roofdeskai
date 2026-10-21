-- Outbound prospecting and outreach. Applied by init.sql on a fresh DB; run by hand on an existing one.
CREATE TABLE IF NOT EXISTS campaigns (
  id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT, city TEXT,
  auto_approve BOOLEAN NOT NULL DEFAULT false, daily_cap INT NOT NULL DEFAULT 20,
  active BOOLEAN NOT NULL DEFAULT true, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS prospects (
  id SERIAL PRIMARY KEY, campaign_id INT NOT NULL REFERENCES campaigns(id), external_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL, category TEXT, address TEXT, phone TEXT, email TEXT, website TEXT, maps_url TEXT,
  rating NUMERIC, review_count INT, hours_json JSONB, review_texts JSONB,
  score INT NOT NULL DEFAULT 0, score_reasons JSONB NOT NULL DEFAULT '[]', pain_mentions INT NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'scored', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS outreach_messages (
  id SERIAL PRIMARY KEY, prospect_id INT NOT NULL REFERENCES prospects(id), step INT NOT NULL,
  channel TEXT NOT NULL DEFAULT 'email', subject TEXT NOT NULL, body TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'template',  -- 'llm' or 'template'
  status TEXT NOT NULL DEFAULT 'drafted',   -- drafted, approved, sent, failed, rejected, cancelled
  scheduled_for TIMESTAMPTZ, sent_at TIMESTAMPTZ, error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (prospect_id, step)
);
CREATE TABLE IF NOT EXISTS suppressions (
  email TEXT PRIMARY KEY, reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS prospect_events (
  id SERIAL PRIMARY KEY, prospect_id INT NOT NULL REFERENCES prospects(id),
  kind TEXT NOT NULL, detail TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE llm_calls ALTER COLUMN conversation_id DROP NOT NULL;
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS prospect_id INT REFERENCES prospects(id);
