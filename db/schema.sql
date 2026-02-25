-- ============================================================
-- SecureIntent Database Schema
-- Run in Supabase SQL Editor
-- ============================================================

-- Profiles table (stores Google refresh token for API execution)
CREATE TABLE IF NOT EXISTS profiles (
  id                  UUID PRIMARY KEY,     -- matches auth.users.id
  email               TEXT UNIQUE NOT NULL,
  google_refresh_token TEXT,                -- Google refresh token for Gmail + Calendar API
  last_history_id     TEXT,                 -- for incremental syncing
  role                TEXT DEFAULT 'user',
  created_at          TIMESTAMPTZ DEFAULT now(),
  updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Plans table (persists intent analysis + approval workflow)
CREATE TABLE IF NOT EXISTS plans (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_email       TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
    -- pending | approved | rejected | executing | executed | failed
  goal_type        TEXT,
  risk_level       TEXT,
  risk_score       FLOAT,
  policy_decision  TEXT,
  subject          TEXT,
  sender           TEXT,
  intent_json      JSONB,       -- full Intent model serialized
  plan_json        JSONB,       -- full GoalPlan model serialized
  execution_log    JSONB,       -- tool execution trace
  reject_reason    TEXT,
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ DEFAULT now()
);

-- Index for fast dashboard queries
CREATE INDEX IF NOT EXISTS plans_user_email_idx ON plans (user_email);
CREATE INDEX IF NOT EXISTS plans_status_idx     ON plans (status);
CREATE INDEX IF NOT EXISTS plans_created_at_idx ON plans (created_at DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER plans_updated_at
  BEFORE UPDATE ON plans
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Row Level Security (optional but recommended)
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;