from pydantic import BaseModel
from typing import List
from enum import Enum

class StepStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"

class StepExecutionResult(BaseModel):
    step_id: int
    status: StepStatus
    message: str

class GoalExecutionResult(BaseModel):
    goal_type: str
    overall_status: StepStatus
    step_results: List[StepExecutionResult]