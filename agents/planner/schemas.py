from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum


class GoalType(str, Enum):
    # ── Email actions ──────────────────────────────────────────────────────────
    SEND_REPLY            = "send_reply"
    SEND_EMAIL            = "send_email"
    FORWARD_EMAIL         = "forward_email"
    CREATE_DRAFT          = "create_draft"
    AUTO_RESPOND          = "auto_respond"

    # ── Calendar ───────────────────────────────────────────────────────────────
    SCHEDULE_CALENDAR_EVENT = "schedule_calendar_event"
    RESCHEDULE_EVENT      = "reschedule_event"
    CANCEL_EVENT          = "cancel_event"

    # ── Finance ───────────────────────────────────────────────────────────────
    INITIATE_PAYMENT      = "initiate_payment"
    REQUEST_INVOICE       = "request_invoice"
    FLAG_EXPENSE          = "flag_expense"

    # ── Task / Project management ──────────────────────────────────────────────
    CREATE_TASK           = "create_task"
    ASSIGN_TASK           = "assign_task"
    UPDATE_TASK_STATUS    = "update_task_status"
    ESCALATE_ISSUE        = "escalate_issue"

    # ── Document / File ───────────────────────────────────────────────────────
    REQUEST_DOCUMENT      = "request_document"
    SHARE_DOCUMENT        = "share_document"
    SUMMARIZE_THREAD      = "summarize_thread"

    # ── Approval workflows ─────────────────────────────────────────────────────
    REQUEST_APPROVAL      = "request_approval"
    SEND_APPROVAL         = "send_approval"
    REJECT_REQUEST        = "reject_request"

    # ── Notifications & alerts ─────────────────────────────────────────────────
    SEND_NOTIFICATION     = "send_notification"
    ESCALATE_TO_MANAGER   = "escalate_to_manager"
    TELEGRAM_SEND_MESSAGE = "telegram_send_message"

    # ── Fallback ──────────────────────────────────────────────────────────────
    RESPOND_WITH_INFORMATION = "respond_with_information"
    NO_ACTION             = "no_action"


class StepAction(str, Enum):
    """
    Typed action for each execution step.
    The executor dispatches on this value to call the right API.
    """
    # Gmail
    GMAIL_SEND_REPLY      = "gmail_send_reply"
    GMAIL_SEND_EMAIL      = "gmail_send_email"
    GMAIL_FORWARD         = "gmail_forward"
    GMAIL_CREATE_DRAFT    = "gmail_create_draft"

    # Google Calendar
    CALENDAR_CREATE_EVENT = "calendar_create_event"
    CALENDAR_UPDATE_EVENT = "calendar_update_event"
    CALENDAR_CANCEL_EVENT = "calendar_cancel_event"
    CALENDAR_CHECK_AVAIL  = "calendar_check_availability"

    # Finance stubs
    PAYMENT_VERIFY        = "payment_verify"
    PAYMENT_INITIATE      = "payment_initiate"
    INVOICE_REQUEST       = "invoice_request"

    # Task management
    TASK_CREATE           = "task_create"
    TASK_ASSIGN           = "task_assign"
    TASK_UPDATE           = "task_update"
    TASK_ESCALATE         = "task_escalate"

    # Document
    DOC_REQUEST           = "doc_request"
    DOC_SHARE             = "doc_share"
    DOC_SUMMARIZE         = "doc_summarize"

    # Approval
    APPROVAL_REQUEST      = "approval_request"
    APPROVAL_SEND         = "approval_send"

    # Notification
    NOTIFY_STAKEHOLDER    = "notify_stakeholder"
    ESCALATE_MANAGER      = "escalate_manager"
    TELEGRAM_SEND_MESSAGE = "telegram_send_message"

    # Generic
    HUMAN_REVIEW          = "human_review"
    LOG_ONLY              = "log_only"


class ExecutionStep(BaseModel):
    step_id: int
    action: StepAction = StepAction.LOG_ONLY   # typed action for executor dispatch
    description: str
    requires_human_approval: bool
    requires_external_action: bool = False      # flags external API calls for policy gate
    params: Dict[str, Any] = {}                 # runtime params passed to executor


class GoalPlan(BaseModel):
    goal_type: GoalType
    steps: List[ExecutionStep]
    priority: int  # 1 (low) – 5 (critical)
    summary: str = ""   # human-readable description shown in sidebar
