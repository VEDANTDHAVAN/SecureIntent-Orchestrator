"""
utils.py
--------
LLM prompt utilities.

- Token-aware text truncation
- Entity formatting for prompts
"""

from __future__ import annotations

from tiktoken import get_encoding


_DEFAULT_ENCODING = "cl100k_base"


def truncate_to_token_limit(
    text: str,
    max_tokens: int,
    encoding_name: str = _DEFAULT_ENCODING,
) -> str:
    """
    Truncate text to fit within a token budget.

    Args:
        text: Input string to potentially truncate
        max_tokens: Maximum allowed tokens
        encoding_name: Tiktoken encoding (default: cl100k_base for GPT-4)

    Returns:
        Original text if within budget, otherwise truncated text with suffix.
    """
    enc = get_encoding(encoding_name)
    tokens = enc.encode(text)

    if len(tokens) <= max_tokens:
        return text

    truncated = enc.decode(tokens[:max_tokens])
    return truncated + "\n[... content truncated to fit token limit ...]"


def count_tokens(text: str, encoding_name: str = _DEFAULT_ENCODING) -> int:
    """Return token count for a string."""
    enc = get_encoding(encoding_name)
    return len(enc.encode(text))


def format_entities_for_prompt(entities: dict) -> str:
    """
    Format extracted entities as a readable block for inclusion in prompts.

    Example output:
        action_requested: Schedule a meeting
        recipients: ['john@example.com']
        dates: ['tomorrow at 3pm']
    """
    if not entities:
        return "(no entities)"
    lines = []
    for key, value in entities.items():
        if value:
            val_str = (
                ", ".join(str(v) for v in value)
                if isinstance(value, list)
                else str(value)
            )
            lines.append(f"  {key}: {val_str}")
    return "\n".join(lines) if lines else "(no entities)"
