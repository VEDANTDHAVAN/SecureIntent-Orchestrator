from typing import List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class IntentType(str, Enum):
    SCHEDULE_MEETING = "schedule_meeting"
    PAYMENT_REQUEST = "payment_request"
    INFORMATION_QUERY = "information_query"
    TASK_REQUEST = "task_request"
    UNKNOWN = "unknown"


class Entities(BaseModel):
    dates: List[str] = Field(default_factory=list)
    amounts: List[float] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)


class Intent(BaseModel):
    intent_type: IntentType
    action_requested: str
    entities: Entities
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    requires_external_action: bool

    @field_validator("action_requested")
    @classmethod
    def action_must_not_be_empty(cls, v: str):
        if not v.strip():
            raise ValueError("action_requested cannot be empty")
        return v
