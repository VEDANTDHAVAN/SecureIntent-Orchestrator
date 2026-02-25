from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict, Literal


class UserOut(BaseModel):
    id: str
    email: str
    role: str = "user"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class HealthResponse(BaseModel):
    status: str
    db_connected: Optional[bool] = None


# --- Base Schemas for DB Tables ---

class EmailBase(BaseModel):
    user_id: str
    sender: str
    subject: str
    body: Optional[str] = None
    received_at: Optional[datetime] = None
    raw_payload: Optional[Dict[str, Any]] = None


class EmailCreate(EmailBase):
    pass


class EmailOut(EmailBase):
    id: str
    created_at: datetime


class IntentBase(BaseModel):
    email_id: str
    intent_type: str
    confidence: float
    structured_output: Optional[Dict[str, Any]] = None


class IntentCreate(IntentBase):
    pass


class IntentOut(IntentBase):
    id: str
    created_at: datetime


class PlanBase(BaseModel):
    intent_id: str
    steps: List[Dict[str, Any]]
    status: str = "pending"


class PlanCreate(PlanBase):
    pass


class PlanOut(PlanBase):
    id: str
    created_at: datetime


class RiskScoreBase(BaseModel):
    email_id: str
    score: int = Field(ge=0, le=100)
    breakdown: Optional[Dict[str, Any]] = None


class RiskScoreCreate(RiskScoreBase):
    pass


class RiskScoreOut(RiskScoreBase):
    id: str
    created_at: datetime


class ActionLogBase(BaseModel):
    user_id: Optional[str] = None
    action_type: str
    status: str
    metadata: Optional[Dict[str, Any]] = None


class ActionLogCreate(ActionLogBase):
    pass


class ActionLogOut(ActionLogBase):
    id: str
    created_at: datetime


# ── Agent pipeline schemas ──────────────────────────────────────

class ExecutionStepOut(BaseModel):
    step_id: int
    description: str
    requires_human_approval: bool


class StepResultOut(BaseModel):
    step_id: int
    status: str
    message: str


class GoalPlanOut(BaseModel):
    goal_type: str
    priority: int
    steps: List[ExecutionStepOut]


class GoalExecutionOut(BaseModel):
    goal_type: str
    overall_status: str
    step_results: List[StepResultOut]


class ProcessEmailResponse(BaseModel):
    """Response from POST /emails/{email_id}/process"""
    email_id: str
    intent_id: str
    plan_id: str
    intent_type: str
    confidence: float
    goal_type: str
    plan_status: str
    execution: Optional[GoalExecutionOut] = None
    status: Literal["processed", "blocked"]
    reason: Optional[str] = None


class ApprovalResponse(BaseModel):
    """Response from approve / reject / execute endpoints"""
    plan_id: str
    status: str
    message: str
    steps_total: Optional[int] = None
    steps_succeeded: Optional[int] = None
    execution: Optional[GoalExecutionOut] = None
