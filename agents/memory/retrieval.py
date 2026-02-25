"""
retrieval.py
------------
Semantic context retrieval for the intent extractor.

Builds a context string from recent user intents that is prepended
to the LLM prompt, so the model can resolve references to past emails
without accessing external systems.
"""

from __future__ import annotations

from agents.memory.memory import agent_memory


def build_context_string(user_id: str, current_subject: str, n: int = 5) -> str:
    """
    Build a formatted context block from a user's recent intents.

    This string is prepended to the intent extractor's user_prompt so
    the LLM has context about recent email activity without being able
    to query systems directly.

    Args:
        user_id: Supabase user ID
        current_subject: Subject of the current email (used for relevance note)
        n: Maximum number of recent intents to include

    Returns:
        Multi-line context string, or empty string if no history.
    """
    recent = agent_memory.get_recent_intents(user_id, n=n)
    if not recent:
        return ""

    lines = ["--- Recent Email Context (most recent first) ---"]
    for i, intent in enumerate(reversed(recent), 1):
        intent_type = intent.get("intent_type", "unknown")
        confidence = intent.get("confidence_score", 0.0)
        entities = intent.get("entities", {})
        lines.append(
            f"{i}. Intent: {intent_type} (confidence={confidence:.2f}) | "
            f"Entities: {_format_entities(entities)}"
        )
    lines.append("--- End Context ---")
    return "\n".join(lines)


def store_intent(user_id: str, intent_dict: dict) -> None:
    """
    Persist an extracted intent to agent memory after successful extraction.

    Call this from webhooks._run_agent_pipeline() after intent extraction.
    """
    agent_memory.store(user_id, key="intent", value=intent_dict)


def _format_entities(entities: dict) -> str:
    """Format entity dict as a compact string for context."""
    if not entities:
        return "none"
    parts = []
    for k, v in entities.items():
        if v:
            val = v if not isinstance(v, list) else ", ".join(str(x) for x in v[:3])
            parts.append(f"{k}={val}")
    return "; ".join(parts) if parts else "none"
