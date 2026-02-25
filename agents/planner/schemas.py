from typing import List
from pydantic import BaseModel
from enum import Enum


class GoalType(str, Enum):
    SCHEDULE_CALENDAR_EVENT = "schedule_calendar_event"
    INITIATE_PAYMENT = "initiate_payment"
    RESPOND_WITH_INFORMATION = "respond_with_information"
    CREATE_TASK = "create_task"
    NO_ACTION = "no_action"


class ExecutionStep(BaseModel):
    step_id: int
    description: str
    requires_human_approval: bool


class GoalPlan(BaseModel):
    goal_type: GoalType
    steps: List[ExecutionStep]
    priority: int  # 1 (low) – 5 (critical)
