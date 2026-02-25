from typing import Dict
from .schemas import Intent
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .validator import validate_intent
from shared.llm.client import llm_client

class IntentExtractor:
    def __init__(self):
        self.max_retries = 2

    async def extract(self, subject: str, body: str) -> Dict:
        user_prompt = USER_PROMPT_TEMPLATE.format(
            subject=subject, body=body
        )

        last_exception = None

        for attempt in range(self.max_retries):
            try:
                intent: Intent = await llm_client.generate_structured(
                    system_prompt=SYSTEM_PROMPT, schema=Intent, 
                    user_prompt=user_prompt
                )
                
                validation = validate_intent(intent)

                return {
                    "intent": intent.model_dump(),
                    "status": validation.status,
                    "reason": validation.reason
                }

            except Exception as e:
                last_exception = e

        raise RuntimeError(
            f"Intent extraction failed after {self.max_retries} attempts: {last_exception}"
        )