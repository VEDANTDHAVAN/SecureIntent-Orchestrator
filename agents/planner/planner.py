from agents.intent_agent.schemas import Intent, IntentType
from .schemas import GoalPlan, GoalType, ExecutionStep

class GoalPlanner:
    # Deterministic logic layer.
    # Converts validated intent into executable system goals.
    # No LLM usage here.
    CONFIDENCE_THRESHOLD = 0.65

    def plan(self, intent: Intent) -> GoalPlan:
        # Safety Gate: Low confidence → no action
        if intent.confidence_score < self.CONFIDENCE_THRESHOLD:
            return GoalPlan(
                goal_type=GoalType.NO_ACTION,
                priority=1,
                steps=[]
            )

        # Schedule Meeting
        if intent.intent_type == IntentType.SCHEDULE_MEETING:
            if not intent.entities.dates or not intent.entities.people:
                return self._manual_review()

            return GoalPlan(
                goal_type=GoalType.SCHEDULE_CALENDAR_EVENT,
                priority=4, steps=[
                    ExecutionStep(
                        step_id=1, description="Validate meeting time and participant availability",
                        requires_human_approval=False,
                    ), 
                    ExecutionStep(
                        step_id=2, description="Create calendar event",
                        requires_human_approval=True,
                    ),
                ]
            )

        # Initiate Payment
        if intent.intent_type == IntentType.INITIATE_PAYMENT:
            if not intent.entities.amounts or not intent.entities.people:
                return self._manual_review()

            return GoalPlan(
                goal_type=GoalType.INITIATE_PAYMENT,
                priority=5, steps=[
                    ExecutionStep(
                        step_id=1, requires_human_approval=True,
                        description="Verify payment amount and recipient",
                    ),
                    ExecutionStep(
                        step_id=2,
                        description="Initiate payment workflow",
                        requires_human_approval=True,
                    ),
                ]
            )

        if intent.intent_type == IntentType.INFORMATION_QUERY:
            return GoalPlan(
                goal_type=GoalType.RESPOND_WITH_INFORMATION,
                priority=2,
                steps=[
                    ExecutionStep(
                        step_id=1,
                        description="Retrieve requested information",
                        requires_human_approval=False,
                    ),
                    ExecutionStep(
                        step_id=2,
                        description="Draft response email",
                        requires_human_approval=False,
                    ),
                ],
            )

        # Task Request
        if intent.intent_type == IntentType.TASK_REQUEST:
            return GoalPlan(
                goal_type=GoalType.CREATE_TASK,
                priority=3,
                steps=[
                    ExecutionStep(
                        step_id=1,
                        description="Create task in task management system",
                        requires_human_approval=False,
                    ),
                ],
            )
        
        return self._manual_review()

    def _manual_review(self) -> GoalPlan:
        return GoalPlan(
            goal_type=GoalType.NO_ACTION,
            priority=1,
            steps=[]
        )