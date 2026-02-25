-- ═══════════════════════════════════════════════════════════════════════════════
-- SecureIntent Orchestrator — Security & Risk Database Schema
-- ═══════════════════════════════════════════════════════════════════════════════

-- ─── Risk Assessments ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS risk_assessments (
    id              SERIAL PRIMARY KEY,
    email_id        VARCHAR(255) NOT NULL,
    sender_email    VARCHAR(255) NOT NULL,
    sender_domain   VARCHAR(255) NOT NULL DEFAULT '',
    risk_score      DECIMAL(5,2) NOT NULL DEFAULT 0.0,
    risk_level      VARCHAR(20) NOT NULL DEFAULT 'low',
    recommended_action VARCHAR(30) NOT NULL DEFAULT 'auto_approve',
    spf_pass        BOOLEAN DEFAULT FALSE,
    dkim_pass       BOOLEAN DEFAULT FALSE,
    suspicious_url_count  INTEGER DEFAULT 0,
    malicious_attachment_count INTEGER DEFAULT 0,
    header_anomaly_count INTEGER DEFAULT 0,
    risk_factors    JSONB DEFAULT '[]'::jsonb,
    full_report     JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_risk_assessments_email ON risk_assessments(email_id);
CREATE INDEX idx_risk_assessments_score ON risk_assessments(risk_score);
CREATE INDEX idx_risk_assessments_level ON risk_assessments(risk_level);
CREATE INDEX idx_risk_assessments_created ON risk_assessments(created_at);


-- ─── Policy Decisions ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS policy_decisions (
    id                  SERIAL PRIMARY KEY,
    action_type         VARCHAR(100) NOT NULL DEFAULT '',
    policy_action       VARCHAR(30) NOT NULL DEFAULT 'allow',
    matched_policy_ids  JSONB DEFAULT '[]'::jsonb,
    matched_policy_names JSONB DEFAULT '[]'::jsonb,
    reason              TEXT DEFAULT '',
    context_snapshot    JSONB DEFAULT '{}'::jsonb,
    total_rules_evaluated INTEGER DEFAULT 0,
    evaluated_at        TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_policy_decisions_action ON policy_decisions(policy_action);
CREATE INDEX idx_policy_decisions_evaluated ON policy_decisions(evaluated_at);


-- ─── Approval Requests ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_requests (
    id                  SERIAL PRIMARY KEY,
    request_id          VARCHAR(36) UNIQUE NOT NULL,
    action_type         VARCHAR(100) NOT NULL DEFAULT '',
    action_description  TEXT DEFAULT '',
    risk_score          DECIMAL(5,2) DEFAULT 0.0,
    risk_level          VARCHAR(20) DEFAULT '',
    policy_ids          JSONB DEFAULT '[]'::jsonb,
    context             JSONB DEFAULT '{}'::jsonb,
    requester_id        VARCHAR(255) DEFAULT '',
    approver_id         VARCHAR(255) DEFAULT '',
    escalation_level    VARCHAR(30) DEFAULT 'l1_direct',
    status              VARCHAR(20) DEFAULT 'pending',
    timeout_minutes     INTEGER DEFAULT 60,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at          TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_approval_requests_status ON approval_requests(status);
CREATE INDEX idx_approval_requests_requester ON approval_requests(requester_id);
CREATE INDEX idx_approval_requests_created ON approval_requests(created_at);


-- ─── Approval Decisions ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approval_decisions (
    id              SERIAL PRIMARY KEY,
    request_id      VARCHAR(36) NOT NULL REFERENCES approval_requests(request_id),
    decision        VARCHAR(20) NOT NULL,
    decided_by      VARCHAR(255) DEFAULT '',
    reason          TEXT DEFAULT '',
    metadata        JSONB DEFAULT '{}'::jsonb,
    decided_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_approval_decisions_request ON approval_decisions(request_id);
CREATE INDEX idx_approval_decisions_decided ON approval_decisions(decided_at);


-- ─── Execution Audit Log ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS execution_audit_log (
    id              SERIAL PRIMARY KEY,
    action_id       VARCHAR(36) NOT NULL DEFAULT '',
    tool_name       VARCHAR(100) NOT NULL DEFAULT '',
    operation       VARCHAR(100) NOT NULL DEFAULT '',
    user_id         VARCHAR(255) DEFAULT '',
    execution_mode  VARCHAR(20) DEFAULT 'live',
    status          VARCHAR(20) DEFAULT 'pending',
    parameters      JSONB DEFAULT '{}'::jsonb,
    output          JSONB DEFAULT NULL,
    error           TEXT DEFAULT '',
    execution_time_ms DECIMAL(10,2) DEFAULT 0.0,
    validation_passed BOOLEAN DEFAULT TRUE,
    rate_limited    BOOLEAN DEFAULT FALSE,
    executed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_log_action ON execution_audit_log(action_id);
CREATE INDEX idx_audit_log_tool ON execution_audit_log(tool_name);
CREATE INDEX idx_audit_log_user ON execution_audit_log(user_id);
CREATE INDEX idx_audit_log_executed ON execution_audit_log(executed_at);
