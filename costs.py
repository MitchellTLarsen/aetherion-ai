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
# Source: OpenAI pricing page
PRICING = {
    # OpenAI GPT-5.4 (Latest)
    "gpt-5.4": {"input": 2.50, "output": 15.00, "cached": 0.25},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50, "cached": 0.075},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25, "cached": 0.02},
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00},

    # OpenAI GPT-5.2
    "gpt-5.2": {"input": 1.75, "output": 14.00, "cached": 0.175},
    "gpt-5.2-pro": {"input": 21.00, "output": 168.00},

    # OpenAI GPT-5.1
    "gpt-5.1": {"input": 1.25, "output": 10.00, "cached": 0.125},

    # OpenAI GPT-5.0
    "gpt-5": {"input": 1.25, "output": 10.00, "cached": 0.125},
    "gpt-5-mini": {"input": 0.25, "output": 2.00, "cached": 0.025},
    "gpt-5-nano": {"input": 0.05, "output": 0.40, "cached": 0.005},
    "gpt-5-pro": {"input": 15.00, "output": 120.00},

    # OpenAI GPT-4.1
    "gpt-4.1": {"input": 2.00, "output": 8.00, "cached": 0.50},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60, "cached": 0.10},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40, "cached": 0.025},

    # OpenAI GPT-4o
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},

    # OpenAI o-series (reasoning)
    "o1": {"input": 15.00, "output": 60.00, "cached": 7.50},
    "o1-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o1-pro": {"input": 150.00, "output": 600.00},
    "o3": {"input": 2.00, "output": 8.00, "cached": 0.50},
    "o3-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o3-pro": {"input": 20.00, "output": 80.00},
    "o4-mini": {"input": 1.10, "output": 4.40, "cached": 0.275},

    # Legacy OpenAI
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},

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

# Context window limits (in tokens) - leave room for output
CONTEXT_LIMITS = {
    # OpenAI GPT-5.4
    "gpt-5.4": 272000,
    "gpt-5.4-mini": 128000,
    "gpt-5.4-nano": 128000,
    "gpt-5.4-pro": 272000,

    # OpenAI GPT-5.2
    "gpt-5.2": 128000,
    "gpt-5.2-pro": 128000,

    # OpenAI GPT-5.1 / 5.0
    "gpt-5.1": 128000,
    "gpt-5": 128000,
    "gpt-5-mini": 128000,
    "gpt-5-nano": 128000,
    "gpt-5-pro": 128000,

    # OpenAI GPT-4.1
    "gpt-4.1": 128000,
    "gpt-4.1-mini": 128000,
    "gpt-4.1-nano": 128000,

    # OpenAI GPT-4o
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,

    # OpenAI o-series
    "o1": 200000,
    "o1-mini": 128000,
    "o1-pro": 200000,
    "o3": 200000,
    "o3-mini": 128000,
    "o3-pro": 200000,
    "o4-mini": 128000,

    # Anthropic
    "claude-sonnet-4-20250514": 200000,
    "claude-3-opus": 200000,
    "claude-3-sonnet": 200000,
    "claude-3-haiku": 200000,

    # Google Gemini
    "gemini-2.5-flash-lite": 1000000,  # 1M context
    "gemini-2.0-flash": 1000000,
    "gemini-1.5-pro": 2000000,  # 2M context

    # Groq
    "llama-3.3-70b-versatile": 128000,
    "mixtral-8x7b-32768": 32768,
    "llama-3.1-8b-instant": 128000,

    # Ollama (varies by model, conservative defaults)
    "llama3": 8192,
    "mistral": 32768,
    "codellama": 16384,
}

DEFAULT_CONTEXT_LIMIT = 32000  # Conservative default

def get_context_limit(model: str) -> int:
    """Get context window limit for a model (in tokens)."""
    return CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)


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
