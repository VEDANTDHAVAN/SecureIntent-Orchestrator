import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from loguru import logger

# Add project root to sys.path
root_path = Path(__file__).parent.parent.parent
sys.path.append(str(root_path))

from agents.intent_agent.extractor import IntentExtractor
from agents.intent_agent.schemas import Intent
from agents.planner.planner import GoalPlanner
from agents.planner.schemas import GoalPlan
from agents.goal_engine.executor import GoalExecutionEngine
from agents.goal_engine.execution_schemas import GoalExecutionResult

# Validate required environment variables
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY not set in environment variables.")

app = FastAPI(
    title="SecureIntent Orchestrator API",
    version="0.3.0",
    description="Agentic Zero-Trust Email Automation System"
)

# ─── Security & Risk Router ──────────────────────────────────────────────────
from apps.api.routes import router as security_router
from engines.policy_guardrails.middleware import PolicyEnforcementMiddleware

app.include_router(security_router)
app.add_middleware(PolicyEnforcementMiddleware)

# Initialize components
intent_extractor = IntentExtractor()
goal_planner = GoalPlanner()
goal_executor = GoalExecutionEngine()

# -----------------------------
# Request / Response Models
# -----------------------------

class EmailRequest(BaseModel):
    subject: str
    body: str


class IntentResponse(BaseModel):
    intent: Intent
    goal_plan: GoalPlan
    execution_result: GoalExecutionResult | None = None
    status: str
    reason: str | None = None


# -----------------------------
# Routes
# -----------------------------

@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/extract-intent", response_model=IntentResponse)
async def extract_intent(email: EmailRequest):
    """
    Extract structured intent from email content
    and convert it into a deterministic goal plan.
    """

    try:
        raw_result = await intent_extractor.extract(
            subject=email.subject,
            body=email.body
        )

        # 🔧 FIX: Normalize to Intent model
        if isinstance(raw_result, dict):
            if "intent" in raw_result:
                intent = Intent(**raw_result["intent"])
            else:
                intent = Intent(**raw_result)
        else: 
            intent = raw_result

        # 2️⃣ Deterministic planning layer
        goal_plan: GoalPlan = goal_planner.plan(intent)

        # 3️⃣ Status evaluation
        if goal_plan.goal_type.name == "NO_ACTION":
            return IntentResponse(
                intent=intent,
                goal_plan=goal_plan,
                execution_result=None,
                status="blocked",
                reason="Low confidence or insufficient entities"
            )

        # Execution plan 
        execution_result = await goal_executor.execute(goal_plan)

        return IntentResponse(
            intent=intent,
            goal_plan=goal_plan,
            execution_result=execution_result,
            status=execution_result.overall_status,
            reason=None
        )

    except Exception as e:
        logger.exception("Intent extraction or planning pipeline failed")
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )
