"""
Token counting and cost estimation for AI providers.
"""

from typing import Optional
from functools import lru_cache

# Cached tiktoken encoding
_encoding_cache = {}


def _get_encoding(model: str):
    """Get tiktoken encoding (cached)."""
    if model not in _encoding_cache:
        try:
            import tiktoken
            if "gpt" in model.lower() or "text-embedding" in model.lower():
                try:
                    _encoding_cache[model] = tiktoken.encoding_for_model(model)
                except KeyError:
                    _encoding_cache[model] = tiktoken.get_encoding("cl100k_base")
            else:
                _encoding_cache[model] = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            _encoding_cache[model] = None
    return _encoding_cache[model]


# Pricing per 1M tokens (input/output) - updated April 2026
# Source: Provider pricing pages
PRICING = {
    # OpenAI
    "gpt-5-nano": {"input": 0.10, "output": 0.40},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},

    # Anthropic
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-opus": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},

    # Google Gemini (free tier has limits, then paid)
    "gemini-2.5-flash-lite": {"input": 0.00, "output": 0.00},  # Free tier
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},

    # Groq (free tier, then paid)
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},

    # Ollama (local - free)
    "llama3": {"input": 0.00, "output": 0.00},
    "mistral": {"input": 0.00, "output": 0.00},
    "codellama": {"input": 0.00, "output": 0.00},

    # OpenRouter (varies by model, these are examples)
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "meta-llama/llama-3-70b": {"input": 0.59, "output": 0.79},
}

# Default pricing for unknown models (conservative estimate)
DEFAULT_PRICING = {"input": 1.00, "output": 3.00}


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """
    Count tokens in text.

    Uses tiktoken for OpenAI models (cached), approximation for others.
    """
    encoding = _get_encoding(model)

    if encoding:
        return len(encoding.encode(text))
    else:
        # Fallback: rough approximation (1 token ≈ 4 chars for English)
        return len(text) // 4


def count_messages_tokens(messages: list[dict], model: str = "gpt-4o") -> int:
    """Count tokens in a list of messages."""
    total = 0
    for msg in messages:
        # Add overhead for message structure (~4 tokens per message)
        total += 4
        total += count_tokens(msg.get("content", ""), model)
        total += count_tokens(msg.get("role", ""), model)

    # Add base overhead
    total += 3

    return total


def estimate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str,
    provider: Optional[str] = None
) -> dict:
    """
    Estimate cost for a request.

    Returns:
        Dict with input_cost, output_cost, total_cost (in USD)
    """
    # Get pricing for model
    pricing = PRICING.get(model, DEFAULT_PRICING)

    # Calculate costs (pricing is per 1M tokens)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": input_cost + output_cost,
        "model": model,
        "is_free": pricing["input"] == 0 and pricing["output"] == 0
    }


def estimate_chat_cost(
    messages: list[dict],
    system_prompt: str = "",
    context: str = "",
    model: str = "gpt-4o",
    expected_output_tokens: int = 500
) -> dict:
    """
    Estimate cost for a chat completion.

    Args:
        messages: Chat messages
        system_prompt: System prompt text
        context: Additional context (e.g., RAG context)
        model: Model name
        expected_output_tokens: Estimated output length (default 500)

    Returns:
        Cost estimate dict
    """
    # Count input tokens
    input_tokens = 0

    if system_prompt:
        input_tokens += count_tokens(system_prompt, model)

    if context:
        input_tokens += count_tokens(context, model)

    input_tokens += count_messages_tokens(messages, model)

    return estimate_cost(input_tokens, expected_output_tokens, model)


def format_cost(cost: dict) -> str:
    """Format cost estimate for display."""
    if cost["is_free"]:
        return f"[green]FREE[/green] ({cost['input_tokens']:,} tokens)"

    total = cost["total_cost"]

    if total < 0.001:
        cost_str = f"< $0.001"
    elif total < 0.01:
        cost_str = f"~${total:.4f}"
    else:
        cost_str = f"~${total:.3f}"

    return f"{cost_str} ({cost['input_tokens']:,} in + ~{cost['output_tokens']:,} out)"


def format_cost_detailed(cost: dict) -> str:
    """Format detailed cost breakdown."""
    lines = [
        f"Model: {cost['model']}",
        f"Input tokens: {cost['input_tokens']:,}",
        f"Expected output: ~{cost['output_tokens']:,} tokens",
    ]

    if cost["is_free"]:
        lines.append("Cost: FREE (local or free tier)")
    else:
        lines.append(f"Input cost: ${cost['input_cost']:.4f}")
        lines.append(f"Output cost: ${cost['output_cost']:.4f}")
        lines.append(f"Total: ${cost['total_cost']:.4f}")

    return "\n".join(lines)


def get_model_for_provider(provider: str) -> str:
    """Get default model for a provider."""
    from config import (
        GPT_MODEL, GEMINI_MODEL, ANTHROPIC_MODEL,
        OLLAMA_MODEL, GROQ_MODEL, OPENROUTER_MODEL
    )

    mapping = {
        "openai": GPT_MODEL,
        "gpt": GPT_MODEL,
        "gemini": GEMINI_MODEL,
        "anthropic": ANTHROPIC_MODEL,
        "claude": ANTHROPIC_MODEL,
        "ollama": OLLAMA_MODEL,
        "groq": GROQ_MODEL,
        "openrouter": OPENROUTER_MODEL,
    }

    return mapping.get(provider, GPT_MODEL)
