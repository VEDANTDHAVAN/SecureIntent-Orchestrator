-- ============================================================
-- SecureIntent Database Schema (Full)
-- Run in Supabase SQL Editor
-- ============================================================

-- 1. Profiles table
CREATE TABLE IF NOT EXISTS profiles (
  id                  UUID PRIMARY KEY,     -- matches auth.users.id
  email               TEXT UNIQUE NOT NULL,
  google_refresh_token TEXT,
  last_history_id      TEXT,
  role                 TEXT DEFAULT 'user',
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now()
);

-- 2. Emails table
CREATE TABLE IF NOT EXISTS emails (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES profiles(id),
  subject     TEXT,
  body        TEXT,
  sender      TEXT,
  thread_id   TEXT,
  message_id  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 3. Extracted Intents table
CREATE TABLE IF NOT EXISTS extracted_intents (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id          UUID REFERENCES emails(id),
  intent_type       TEXT,
  confidence        FLOAT,
  structured_output JSONB,
  created_at        TIMESTAMPTZ DEFAULT now()
);

-- 4. Plans table
CREATE TABLE IF NOT EXISTS plans (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_email       TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
  goal_type        TEXT,
  risk_level       TEXT,
  risk_score       FLOAT,
  policy_decision  TEXT,
  subject          TEXT,
  sender           TEXT,
  intent_json      JSONB,
  plan_json        JSONB,
  execution_log    JSONB,
  reject_reason    TEXT,
  intent_id        UUID REFERENCES extracted_intents(id),
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);

-- 5. Risk Scores table
CREATE TABLE IF NOT EXISTS risk_scores (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_id    UUID REFERENCES emails(id),
  score       FLOAT,
  level       TEXT,
  reasons     JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- 6. Action Logs table
CREATE TABLE IF NOT EXISTS action_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID,
  action_type TEXT,
  status      TEXT,
  metadata    JSONB,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- 7. Helpers & Indexes
CREATE INDEX IF NOT EXISTS plans_user_email_idx ON plans (user_email);
CREATE INDEX IF NOT EXISTS plans_status_idx     ON plans (status);
CREATE INDEX IF NOT EXISTS plans_created_at_idx ON plans (created_at DESC);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER plans_updated_at
  BEFORE UPDATE ON plans
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER action_logs_updated_at
  BEFORE UPDATE ON action_logs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();