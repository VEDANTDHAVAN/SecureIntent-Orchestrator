from typing import List
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class IntentType(str, Enum):
    SCHEDULE_MEETING = "schedule_meeting"
    PAYMENT_REQUEST = "payment_request"
    INITIATE_PAYMENT = "initiate_payment"      # LLM sometimes returns this variant
    INFORMATION_QUERY = "information_query"
    TASK_REQUEST = "task_request"
    SEND_EMAIL = "send_email"
    REPLY_EMAIL = "reply_email"
    FORWARD_EMAIL = "forward_email"
    FILE_REQUEST = "file_request"
    APPROVAL_REQUEST = "approval_request"
    TELEGRAM_ALERT = "telegram_alert"
    UNKNOWN = "unknown"


class Entities(BaseModel):
    dates: List[str] = Field(default_factory=list)
    amounts: List[float] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)
    organizations: List[str] = Field(default_factory=list)
    urls: List[str] = Field(default_factory=list)


class Intent(BaseModel):
    intent_type: IntentType
    action_requested: str = ""
    # 'action_required' is an alias some LLM responses use
    action_required: str = ""
    entities: Entities = Field(default_factory=Entities)
    confidence_score: float = Field(default=0.5, ge=0.0, le=1.0)
    requires_external_action: bool = False

    @field_validator("intent_type", mode="before")
    @classmethod
    def normalize_intent_type(cls, v):
        """Map unknown LLM values to UNKNOWN instead of crashing."""
        if isinstance(v, str):
            # Try exact match first (case-insensitive)
            normalized = v.lower().strip()
            for member in IntentType:
                if member.value == normalized or member.name.lower() == normalized:
                    return member
            return IntentType.UNKNOWN
        return v

