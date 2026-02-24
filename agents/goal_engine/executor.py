from .schemas import GoalPlan
from .execution_schemas import (
    GoalExecutionResult, StepExecutionResult, StepStatus
)

class GoalExecutionEngine:
    """Deterministic execution layer. Executes planned steps safely. No LLM."""
    
    async def execute(self, goal_plan: GoalPlan) -> GoalExecutionResult:
        step_results = []
        overall_status = StepStatus.COMPLETED

        for step in goal_plan.steps:
            # human approval gate
            if step.requires_human_approval:
                step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id,
                        status=StepStatus.BLOCKED,
                        message="Awaiting human approval",
                    )
                )
                overall_status= StepStatus.BLOCKED
                continue

            # Simulated execution
            try: 
                result = await self._execute_step(step.description)

                step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id, message=result,
                        status=StepStatus.COMPLETED,
                    )
                )

            except Exception as e:
                overall_status = StepStatus.FAILED
                step_results.append(
                    StepExecutionResult(
                        step_id=step.step_id, message=str(e),
                        status=StepStatus.FAILED,
                    )
                )

        return GoalExecutionResult(
            goal_type=goal_plan.goal_type.name,
            overall_status=overall_status,
            step_results=step_results,
        )

    async def _execute_step(self, description: str) -> str:
        """
        Stub execution logic.
        Replace with real integrations (calendar, payments, etc.)
        """
        # Here you'd integrate:
        # - Google Calendar API
        # - Payment processor
        # - Task management system
        return f"Executed: {description}"