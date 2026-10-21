CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE leads (
  id SERIAL PRIMARY KEY, name TEXT, phone TEXT, email TEXT, address TEXT,
  service_type TEXT, property_type TEXT, is_owner BOOLEAN, timeline_months INT, budget_range TEXT,
  status TEXT NOT NULL DEFAULT 'new', qualification_score INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE conversations (
  id SERIAL PRIMARY KEY, lead_id INT REFERENCES leads(id), channel TEXT NOT NULL DEFAULT 'web',
  state TEXT NOT NULL DEFAULT 'GREETING', started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ended_at TIMESTAMPTZ, outcome TEXT, failed_turns INT NOT NULL DEFAULT 0,
  offered_slot_ids INT[] NOT NULL DEFAULT '{}',
  followup_count INT NOT NULL DEFAULT 0,
  external_id TEXT UNIQUE,
  token TEXT NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex')
);
CREATE TABLE messages (
  id SERIAL PRIMARY KEY, conversation_id INT NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE slots (
  id SERIAL PRIMARY KEY, start_time TIMESTAMPTZ NOT NULL, end_time TIMESTAMPTZ NOT NULL,
  is_booked BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE appointments (
  id SERIAL PRIMARY KEY, lead_id INT NOT NULL UNIQUE REFERENCES leads(id),
  slot_id INT NOT NULL UNIQUE REFERENCES slots(id), status TEXT NOT NULL DEFAULT 'booked',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE faq_chunks (
  id SERIAL PRIMARY KEY, source TEXT NOT NULL, text TEXT NOT NULL, embedding vector(384)
);
CREATE TABLE tool_calls (
  id SERIAL PRIMARY KEY, conversation_id INT NOT NULL REFERENCES conversations(id),
  tool_name TEXT NOT NULL, args_json JSONB, result_json JSONB, ok BOOLEAN, latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE llm_calls (
  id SERIAL PRIMARY KEY, conversation_id INT NOT NULL REFERENCES conversations(id),
  model TEXT NOT NULL, prompt_version TEXT, prompt_tokens INT, completion_tokens INT,
  latency_ms INT, schema_valid BOOLEAN, cost_estimate NUMERIC NOT NULL DEFAULT 0
);
CREATE TABLE escalations (
  id SERIAL PRIMARY KEY, conversation_id INT NOT NULL REFERENCES conversations(id),
  reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), resolved BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE events (
  id SERIAL PRIMARY KEY, conversation_id INT NOT NULL REFERENCES conversations(id),
  kind TEXT NOT NULL, detail TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE eval_runs (
  id SERIAL PRIMARY KEY, git_sha TEXT, model TEXT, prompt_version TEXT, metrics_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE eval_results (
  id SERIAL PRIMARY KEY, run_id INT NOT NULL REFERENCES eval_runs(id), scenario_id TEXT NOT NULL,
  passed BOOLEAN NOT NULL, details_json JSONB
);

-- Synthetic slots: weekdays at 9/11/14/16 for the next 14 days.
INSERT INTO slots (start_time, end_time)
SELECT d + make_interval(hours => h), d + make_interval(hours => h + 1)
FROM generate_series(date_trunc('day', now()) + interval '1 day',
                     date_trunc('day', now()) + interval '14 days', interval '1 day') d,
     unnest(ARRAY[9, 11, 14, 16]) h
WHERE extract(isodow FROM d) < 6;

-- Outbound prospecting tables: outreach.sql runs right after this file (alphabetical order).
