"""
GoalPlanner — Deterministic intent → plan mapper.

No LLM is used here. Each IntentType maps to a specific GoalType with
concrete, ordered ExecutionSteps. The policy engine and executor
downstream use step.action and step.requires_external_action to decide
whether to block, gate for approval, or auto-execute.
"""

from agents.intent_agent.schemas import Intent, IntentType
from .schemas import GoalPlan, GoalType, ExecutionStep, StepAction


class GoalPlanner:
    CONFIDENCE_THRESHOLD = 0.55   # lowered slightly — LLM sometimes returns 0.6 for valid intents

    def plan(self, intent: Intent) -> GoalPlan:
        if intent.confidence_score < self.CONFIDENCE_THRESHOLD:
            return GoalPlan(
                goal_type=GoalType.NO_ACTION,
                priority=1,
                steps=[],
                summary="Low confidence — manual review needed.",
            )

        mapper = {
            # ── Email ──────────────────────────────────────────────────────────
            IntentType.SEND_EMAIL:        self._plan_send_email,
            IntentType.REPLY_EMAIL:       self._plan_send_reply,
            IntentType.FORWARD_EMAIL:     self._plan_forward_email,

            # ── Calendar ───────────────────────────────────────────────────────
            IntentType.SCHEDULE_MEETING:  self._plan_schedule_meeting,

            # ── Finance ───────────────────────────────────────────────────────
            IntentType.PAYMENT_REQUEST:   self._plan_payment,
            IntentType.INITIATE_PAYMENT:  self._plan_payment,

            # ── Task ──────────────────────────────────────────────────────────
            IntentType.TASK_REQUEST:      self._plan_task,
            IntentType.APPROVAL_REQUEST:  self._plan_approval_request,

            # ── Information ───────────────────────────────────────────────────
            IntentType.INFORMATION_QUERY: self._plan_info_query,
            IntentType.FILE_REQUEST:      self._plan_file_request,
        }

        handler = mapper.get(intent.intent_type)
        if handler:
            return handler(intent)

        # Default fallback — escalate to human review
        return self._manual_review(intent)

    # ── Email Plans ────────────────────────────────────────────────────────────

    def _plan_send_reply(self, intent: Intent) -> GoalPlan:
        action_text = intent.action_requested or intent.action_required or "reply"
        return GoalPlan(
            goal_type=GoalType.SEND_REPLY,
            priority=3,
            summary=f"Draft and send a reply: {action_text[:80]}",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.DOC_SUMMARIZE,
                    description="Summarize email thread for context",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.GMAIL_CREATE_DRAFT,
                    description="Generate reply draft using thread context",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.GMAIL_SEND_REPLY,
                    description="Send reply to sender",
                    requires_human_approval=True, requires_external_action=True,
                ),
            ],
        )

    def _plan_send_email(self, intent: Intent) -> GoalPlan:
        recipients = intent.entities.people or ["<unknown>"]
        return GoalPlan(
            goal_type=GoalType.SEND_EMAIL,
            priority=3,
            summary=f"Compose and send email to {', '.join(recipients[:2])}",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.GMAIL_CREATE_DRAFT,
                    description=f"Compose email to {', '.join(recipients[:3])}",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.HUMAN_REVIEW,
                    description="Review draft before sending",
                    requires_human_approval=True, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.GMAIL_SEND_EMAIL,
                    description="Send composed email",
                    requires_human_approval=True, requires_external_action=True,
                ),
            ],
        )

    def _plan_forward_email(self, intent: Intent) -> GoalPlan:
        recipients = intent.entities.people or ["<unknown>"]
        return GoalPlan(
            goal_type=GoalType.FORWARD_EMAIL,
            priority=2,
            summary=f"Forward email to {', '.join(recipients[:2])}",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.DOC_SUMMARIZE,
                    description="Add forwarding context note",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.GMAIL_FORWARD,
                    description=f"Forward to {', '.join(recipients[:3])}",
                    requires_human_approval=True, requires_external_action=True,
                ),
            ],
        )

    # ── Calendar Plans ─────────────────────────────────────────────────────────

    def _plan_schedule_meeting(self, intent: Intent) -> GoalPlan:
        from datetime import datetime, timedelta, timezone

        dates   = intent.entities.dates   or []
        people  = intent.entities.people  or []

        if not dates:
            return self._manual_review(intent, reason="No date/time detected in email")

        # Parse the first date and create a reasonable event time
        # LLM extracts dates like "tomorrow at 3pm" or "2024-01-15"
        # We try to parse it, falling back to next business day 10am
        event_date = dates[0]
        start_iso, end_iso = self._parse_datetime(event_date)

        return GoalPlan(
            goal_type=GoalType.SCHEDULE_CALENDAR_EVENT,
            priority=4,
            summary=f"Schedule meeting on {dates[0]} with {', '.join(people[:2]) or 'attendees'}",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.CALENDAR_CHECK_AVAIL,
                    description=f"Check calendar availability for {dates[0]}",
                    requires_human_approval=False, requires_external_action=True,
                    params={
                        "start_iso": start_iso,
                        "end_iso": end_iso,
                    },
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.CALENDAR_CREATE_EVENT,
                    description=f"Create calendar event and invite {', '.join(people[:3]) or 'attendees'}",
                    requires_human_approval=True, requires_external_action=True,
                    params={
                        "title": intent.action_required or "Meeting",
                        "start_iso": start_iso,
                        "end_iso": end_iso,
                        "attendees": people,
                        "description": intent.action_required or "",
                    },
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.GMAIL_SEND_REPLY,
                    description="Send meeting confirmation reply to sender",
                    requires_human_approval=True, requires_external_action=True,
                ),
            ],
        )

    # ── Finance Plans ─────────────────────────────────────────────────────────

    def _plan_payment(self, intent: Intent) -> GoalPlan:
        amounts = intent.entities.amounts or []
        people  = intent.entities.people  or ["<unknown>"]

        return GoalPlan(
            goal_type=GoalType.INITIATE_PAYMENT,
            priority=5,  # Always critical
            summary=(
                f"Payment of {amounts[0] if amounts else '?'} to {people[0]} — "
                "requires multi-step approval"
            ),
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.PAYMENT_VERIFY,
                    description=f"Verify recipient ({people[0]}) and amount ({amounts[0] if amounts else 'unknown'})",
                    requires_human_approval=True, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.HUMAN_REVIEW,
                    description="Finance team approval required",
                    requires_human_approval=True, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.PAYMENT_INITIATE,
                    description="Initiate secure payment transfer",
                    requires_human_approval=True, requires_external_action=True,
                ),
                ExecutionStep(
                    step_id=4, action=StepAction.GMAIL_SEND_REPLY,
                    description="Send payment confirmation to sender",
                    requires_human_approval=False, requires_external_action=True,
                ),
            ],
        )

    # ── Task Plans ────────────────────────────────────────────────────────────

    def _plan_task(self, intent: Intent) -> GoalPlan:
        action_text  = intent.action_requested or intent.action_required or "task"
        assignees    = intent.entities.people or []
        due_dates    = intent.entities.dates  or []

        steps = [
            ExecutionStep(
                step_id=1, action=StepAction.TASK_CREATE,
                description=f"Create task: '{action_text[:60]}'",
                requires_human_approval=False, requires_external_action=True,
            ),
        ]
        if assignees:
            steps.append(ExecutionStep(
                step_id=2, action=StepAction.TASK_ASSIGN,
                description=f"Assign task to {', '.join(assignees[:2])}",
                requires_human_approval=False, requires_external_action=True,
            ))
        if due_dates:
            steps.append(ExecutionStep(
                step_id=len(steps) + 1, action=StepAction.NOTIFY_STAKEHOLDER,
                description=f"Notify stakeholders of deadline: {due_dates[0]}",
                requires_human_approval=False, requires_external_action=True,
            ))
        steps.append(ExecutionStep(
            step_id=len(steps) + 1, action=StepAction.GMAIL_SEND_REPLY,
            description="Acknowledge task receipt to sender",
            requires_human_approval=False, requires_external_action=True,
        ))

        return GoalPlan(
            goal_type=GoalType.CREATE_TASK,
            priority=3,
            summary=f"Create and assign task: {action_text[:60]}",
            steps=steps,
        )

    def _plan_approval_request(self, intent: Intent) -> GoalPlan:
        action_text = intent.action_requested or intent.action_required or "approval"
        people = intent.entities.people or []

        return GoalPlan(
            goal_type=GoalType.REQUEST_APPROVAL,
            priority=4,
            summary=f"Route approval request: {action_text[:60]}",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.DOC_SUMMARIZE,
                    description="Summarize approval request details",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.APPROVAL_REQUEST,
                    description=f"Route to approver(s): {', '.join(people[:2]) or 'manager'}",
                    requires_human_approval=True, requires_external_action=True,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.NOTIFY_STAKEHOLDER,
                    description="Notify requestor of approval status",
                    requires_human_approval=False, requires_external_action=True,
                ),
            ],
        )

    # ── Information / Document Plans ──────────────────────────────────────────

    def _plan_info_query(self, intent: Intent) -> GoalPlan:
        return GoalPlan(
            goal_type=GoalType.RESPOND_WITH_INFORMATION,
            priority=2,
            summary="Retrieve information and draft a response",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.DOC_SUMMARIZE,
                    description="Analyze query and gather relevant context",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.GMAIL_CREATE_DRAFT,
                    description="Draft informational response",
                    requires_human_approval=False, requires_external_action=False,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.GMAIL_SEND_REPLY,
                    description="Send response to sender",
                    requires_human_approval=True, requires_external_action=True,
                ),
            ],
        )

    def _plan_file_request(self, intent: Intent) -> GoalPlan:
        people = intent.entities.people or []
        return GoalPlan(
            goal_type=GoalType.REQUEST_DOCUMENT,
            priority=2,
            summary="Handle document/file request",
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.DOC_REQUEST,
                    description="Locate requested document or file",
                    requires_human_approval=False, requires_external_action=True,
                ),
                ExecutionStep(
                    step_id=2, action=StepAction.DOC_SHARE,
                    description=f"Share document with {', '.join(people[:2]) or 'requester'}",
                    requires_human_approval=True, requires_external_action=True,
                ),
                ExecutionStep(
                    step_id=3, action=StepAction.GMAIL_SEND_REPLY,
                    description="Confirm file was shared via email",
                    requires_human_approval=False, requires_external_action=True,
                ),
            ],
        )

    # ── Date/Time Parsing Helper ────────────────────────────────────────────────

    def _parse_datetime(self, date_str: str) -> tuple[str, str]:
        """
        Parse a natural language date string into ISO start/end times.
        Returns (start_iso, end_iso) for a 1-hour meeting slot.

        Handles:
          - "tomorrow at 3pm"
          - "2024-01-15"
          - "next monday at 10am"
          - "january 20th"
        Falls back to next business day 10am if parsing fails.
        """
        from datetime import datetime, timedelta, timezone
        import re

        now = datetime.now(timezone.utc)
        date_str_lower = date_str.lower().strip()

        # Default: next business day at 10am UTC
        default_start = now.replace(hour=10, minute=0, second=0, microsecond=0)
        if default_start <= now:
            default_start += timedelta(days=1)
        # Skip weekends
        while default_start.weekday() >= 5:
            default_start += timedelta(days=1)

        # Try common patterns
        hour_match = re.search(r'(\d{1,2})\s*(am|pm)?', date_str_lower)
        hour = 10
        if hour_match:
            hour = int(hour_match.group(1))
            if hour_match.group(2) == 'pm' and hour < 12:
                hour += 12
            elif hour_match.group(2) == 'am' and hour == 12:
                hour = 0

        # "tomorrow"
        if 'tomorrow' in date_str_lower:
            start = now + timedelta(days=1)
            start = start.replace(hour=hour, minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=1)
            return start.isoformat(), end.isoformat()

        # "next monday/tuesday/etc"
        weekday_map = {'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                       'friday': 4, 'saturday': 5, 'sunday': 6}
        for day_name, day_num in weekday_map.items():
            if day_name in date_str_lower:
                days_ahead = day_num - now.weekday()
                if days_ahead <= 0:
                    days_ahead += 7
                start = now + timedelta(days=days_ahead)
                start = start.replace(hour=hour, minute=0, second=0, microsecond=0)
                end = start + timedelta(hours=1)
                return start.isoformat(), end.isoformat()

        # ISO date format: "2024-01-15" or "2024-01-15T14:00"
        iso_match = re.match(r'(\d{4}-\d{2}-\d{2})(?:t(\d{2}:\d{2}))?', date_str_lower)
        if iso_match:
            date_part = iso_match.group(1)
            time_part = iso_match.group(2)
            if time_part:
                start = datetime.fromisoformat(f"{date_part}T{time_part}+00:00")
            else:
                start = datetime.fromisoformat(f"{date_part}T{hour:02d}:00:00+00:00")
            end = start + timedelta(hours=1)
            return start.isoformat(), end.isoformat()

        # Month name patterns: "january 20th", "jan 20"
        month_map = {'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
                     'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
                     'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
                     'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
                     'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
                     'dec': 12, 'december': 12}
        for month_name, month_num in month_map.items():
            if month_name in date_str_lower:
                day_match = re.search(r'(\d{1,2})', date_str_lower)
                day = int(day_match.group(1)) if day_match else 15
                try:
                    start = now.replace(year=now.year, month=month_num, day=day,
                                        hour=hour, minute=0, second=0, microsecond=0)
                    if start < now:
                        start = start.replace(year=now.year + 1)
                    end = start + timedelta(hours=1)
                    return start.isoformat(), end.isoformat()
                except ValueError:
                    pass

        # Fallback to default
        end = default_start + timedelta(hours=1)
        return default_start.isoformat(), end.isoformat()

    # ── Fallback ──────────────────────────────────────────────────────────────

    def _manual_review(self, intent: Intent, reason: str = "") -> GoalPlan:
        label = reason or f"Intent '{intent.intent_type.value}' requires human review"
        return GoalPlan(
            goal_type=GoalType.NO_ACTION,
            priority=1,
            summary=label,
            steps=[
                ExecutionStep(
                    step_id=1, action=StepAction.HUMAN_REVIEW,
                    description=label,
                    requires_human_approval=True, requires_external_action=False,
                ),
            ],
        )