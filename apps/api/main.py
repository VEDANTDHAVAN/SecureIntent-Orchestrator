import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load from root .env
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
from pydantic import BaseModel
from loguru import logger
import uuid

# In-memory plan store is now in db.models.PLAN_CACHE (shared with agent_routes.py)

# Add project root to sys.path so all packages resolve
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

# ── Validate required env vars early ─────────────────────────────────────────
_missing = [v for v in ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_KEY") if not os.getenv(v)]
if _missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(_missing)}")

# ── Agent imports ─────────────────────────────────────────────────────────────
from agents.intent_agent.extractor import IntentExtractor
from agents.intent_agent.schemas import Intent
from agents.planner.planner import GoalPlanner
from agents.planner.schemas import GoalPlan
from agents.goal_engine.executor import GoalExecutionEngine
from agents.goal_engine.execution_schemas import GoalExecutionResult

# ── Modular routers ───────────────────────────────────────────────────────────
from apps.api.auth import auth_router, get_current_user_optional
from apps.api.routes import health_router, email_router
from apps.api.schemas import UserOut
from apps.api.agent_routes import agent_router, plan_router
from apps.api.webhooks import webhook_router
from db.models import ping_db, PLAN_CACHE as _PLAN_CACHE, get_plan_cached as _get_plan_with_cache

# ── Agent singletons ──────────────────────────────────────────────────────────
intent_extractor = IntentExtractor()
goal_planner = GoalPlanner()
goal_executor = GoalExecutionEngine()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SecureIntent Orchestrator v0.2.0")
    connected = ping_db()
    logger.info("✅ Supabase connected" if connected else "⚠️  Supabase NOT reachable")
    yield
    logger.info("Shutting down")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="SecureIntent Orchestrator API",
    version="0.2.0",
    description="Agentic Zero-Trust Email Automation System",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        os.getenv("FRONTEND_URL", "http://localhost:3000"),
        "http://localhost:8000",
        "http://localhost",
        # Chrome extension — the extension ID changes per install so we allow the scheme
        "chrome-extension://",
    ],
    allow_origin_regex=r"(chrome-extension://.*|http://localhost(:\d+)?)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(webhook_router)
app.include_router(email_router)
app.include_router(agent_router)
app.include_router(plan_router)


# ── Global exception handlers ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# ── /analyze — full security pipeline for Chrome extension ───────────────────
# Returns everything the sidebar needs in one call:
#   risk_score, policy_decision, intent, goal_plan, plan_id (if persisted)

class AnalyzeRequest(BaseModel):
    subject: str
    body: str
    sender: str = ""
    # Optional context for real execution
    thread_id: str = ""
    message_id: str = ""
    save_plan: bool = True     # persist to DB by default


@app.post("/analyze", tags=["Extension"])
async def analyze_email(
    req: AnalyzeRequest,
    current_user: Optional[UserOut] = Depends(get_current_user_optional)
):
    """
    Stateless analysis endpoint for the Chrome extension sidebar.

    Runs the full zero-trust pipeline on raw email text:
      1. Trust/Risk Scoring
      2. LLM Intent Extraction
      3. Deterministic Planning
      4. Policy Engine

    Returns a response the sidebar can directly render.
    Does NOT execute any tool or send any email.
    """
    from engines.trust_risk.spf_dkim import SpfDkimResult
    from engines.trust_risk.url_scanner import extract_urls, scan_urls
    from engines.trust_risk.scorer import calculate_risk
    from engines.policy_guardrails.middleware import apply_policy_gate

    # ── Gate 1: Risk scoring ──────────────────────────────────────────────────
    spf_dkim = SpfDkimResult()               # No raw headers from extension DOM
    urls = extract_urls(req.body)
    url_scan = scan_urls(urls)
    risk = calculate_risk(
        spf_dkim, url_scan,
        sender=req.sender,
        subject=req.subject
    )

    risk_payload = {
        "level": risk.level.value,
        "score": round(risk.score, 4),
        "reasons": risk.reasons,
        "spf": risk.spf,
        "dkim": risk.dkim,
    }

    # CRITICAL — don't even run LLM
    if risk.blocks_pipeline:
        return {
            "status": "blocked",
            "policy_decision": "block",
            "block_reason": f"CRITICAL risk score ({risk.score:.2f})",
            "risk_score": risk_payload,
            "intent": None,
            "goal_plan": None,
            "plan_id": None,
        }

    # ── Gate 2: LLM Intent + Plan ─────────────────────────────────────────────
    try:
        raw = await intent_extractor.extract(subject=req.subject, body=req.body)
        intent_dict = raw.get("intent", raw)
        intent = Intent(**intent_dict)
        goal_plan = goal_planner.plan(intent)
    except Exception as exc:
        logger.error("Intent extraction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Intent extraction failed: {exc}")

    # ── Gate 3: Policy engine ─────────────────────────────────────────────────
    goal_type_str = goal_plan.goal_type.value
    requires_external = any(
        getattr(s, "requires_external_action", False) for s in goal_plan.steps
    )
    policy = apply_policy_gate(
        goal_type=goal_type_str,
        risk_score=risk,
        requires_external_action=requires_external,
        confidence=intent.confidence_score,
    )

    policy_decision = policy.decision.value.lower()   # "allow" | "block" | "require_approval"

    # ── Persist plan to Supabase ──────────────────────────────────────────────
    # Always generate a plan_id, even if DB write fails
    plan_id = str(uuid.uuid4())

    # Associate plan with the authenticated user if logged in, else fall back to sender
    user_email = "anonymous"
    if current_user:
        user_email = current_user.email
    elif req.sender:
        user_email = req.sender

    plan_data = {
        "id": plan_id,
        "user_email": user_email,
        "status": "pending",
        "goal_type": goal_type_str,
        "risk_level": risk.level.value,
        "risk_score": round(risk.score, 4),
        "policy_decision": policy_decision,
        "subject": req.subject[:255],
        "sender": req.sender[:255] if req.sender else "",
        "intent_json": {
            "intent_type": intent.intent_type.value,
            "confidence_score": intent.confidence_score,
            "action_required": intent.action_required,
        },
        "plan_json": {
            "goal_type": goal_type_str,
            "priority": goal_plan.priority,
            "summary": getattr(goal_plan, "summary", ""),
            "steps": [s.model_dump() for s in goal_plan.steps],
            "email_context": {
                "subject": req.subject,
                "sender": req.sender,
                "thread_id": req.thread_id,
                "message_id": req.message_id,
            },
        },
    }

    if req.save_plan:
        try:
            from db.models import save_plan as db_save_plan
            db_row = db_save_plan(plan_data)
            # DB may assign a different id (e.g. auto-increment)
            plan_id = db_row.get("id", plan_id)
            plan_data["id"] = plan_id
            logger.info("Plan saved to DB: id=%s goal=%s policy=%s", plan_id, goal_type_str, policy_decision)
        except Exception as db_exc:
            logger.warning("Plan DB persistence failed — using in-memory store: %s", db_exc)

    # Always cache in-memory so approve/execute can find it regardless of DB state
    _PLAN_CACHE[plan_id] = plan_data
    logger.info("Plan cached: id=%s (cache size=%d)", plan_id, len(_PLAN_CACHE))

    return {
        "status": "analyzed",
        "policy_decision": policy_decision,
        "policy_explanation": policy.explanation,
        "triggered_rules": policy.triggered_rules,
        "risk_score": risk_payload,
        "intent": {
            "intent_type": intent.intent_type.value,
            "confidence_score": intent.confidence_score,
            "action_required": intent.action_required,
            "entities": intent.entities,
        },
        "goal_plan": {
            "goal_type": goal_type_str,
            "priority": goal_plan.priority,
            "summary": getattr(goal_plan, "summary", ""),
            "steps": [s.model_dump() for s in goal_plan.steps],
        },
        "plan_id": plan_id,
    }


# ── Plan management endpoints ──────────────────────────────────────────────────

# /analyze is the remaining endpoint in this file. 
# Plan management routes are now in agent_routes.py and included via plan_router.
