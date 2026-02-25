import asyncio
import json
from typing import Type, TypeVar
from pydantic import BaseModel, ValidationError
from openai import AsyncOpenAI
from loguru import logger
from tiktoken import get_encoding
import os

T = TypeVar("T", bound=BaseModel)

class LLMClient:
    """
    Production-ready LLM client with:
    - Structured output enforcement
    - Schema validation
    - Retry logic
    - Token tracking
    - Timeout handling
    """
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )

        self.model = "gpt-4o-mini" 
        self.temperature = 0.0
        self.max_tokens = 1000
        self.timeout_seconds = 30
        self.max_retries = 2

        self.encoding = get_encoding("cl100k_base")

    async def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: Type[T],
    ) -> T:
        """
        Generate structured output validated against a Pydantic schema.
        """

        for attempt in range(self.max_retries):
            try:
                response = await asyncio.wait_for(
                    self.client.chat.completions.create(
                        model=self.model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.timeout_seconds,
                )

                content = response.choices[0].message.content

                if not content:
                    raise ValueError("Empty response from LLM")

                parsed_json = json.loads(content)

                # Validate against schema
                validated = schema.model_validate(parsed_json)

                self._log_usage(response)

                return validated

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(
                    f"Structured output validation failed (attempt {attempt+1}): {e}"
                )
                if attempt == self.max_retries - 1:
                    raise

            except asyncio.TimeoutError:
                logger.error("LLM request timed out")
                if attempt == self.max_retries - 1:
                    raise

            except Exception as e:
                logger.error(f"Unexpected LLM error: {e}")
                if attempt == self.max_retries - 1:
                    raise

        raise RuntimeError("LLM generation failed after retries")

    def _log_usage(self, response):
        # Log token usage for monitoring and cost tracking.
        if hasattr(response, "usage") and response.usage:
            logger.info(
                f"LLM Usage | Prompt: {response.usage.prompt_tokens} "
                f"| Completion: {response.usage.completion_tokens} "
                f"| Total: {response.usage.total_tokens}"
            )

# Singleton instance
llm_client = LLMClient()