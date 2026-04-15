"""
AI Provider abstraction for multiple LLM backends.

Supported providers:
- openai: OpenAI GPT models (gpt-4o, gpt-4o-mini, gpt-5-nano, etc.)
- gemini: Google Gemini models (gemini-2.5-flash-lite, gemini-2.0-flash, etc.)
- anthropic: Anthropic Claude models (claude-sonnet-4-20250514, etc.)
- ollama: Local models via Ollama (llama3, mistral, etc.)
- groq: Fast inference (llama-3.3-70b-versatile, mixtral-8x7b, etc.)
- openrouter: Access to many models via OpenRouter
"""

from typing import Generator, Optional
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    name: str
    api_key: Optional[str]
    base_url: Optional[str]
    default_model: str
    supports_streaming: bool = True
    supports_system_prompt: bool = True


# Provider registry
_providers: dict[str, "BaseProvider"] = {}


def get_provider(name: str) -> "BaseProvider":
    """Get a provider by name, initializing if needed."""
    if name not in _providers:
        _providers[name] = _create_provider(name)
    return _providers[name]


def _create_provider(name: str) -> "BaseProvider":
    """Create a provider instance."""
    from config import (
        OPENAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
        OLLAMA_BASE_URL, GROQ_API_KEY, OPENROUTER_API_KEY,
        GPT_MODEL, GEMINI_MODEL, ANTHROPIC_MODEL,
        OLLAMA_MODEL, GROQ_MODEL, OPENROUTER_MODEL
    )

    if name == "openai" or name == "gpt":
        return OpenAIProvider(
            api_key=OPENAI_API_KEY,
            default_model=GPT_MODEL
        )
    elif name == "gemini":
        return GeminiProvider(
            api_key=GEMINI_API_KEY,
            default_model=GEMINI_MODEL
        )
    elif name == "anthropic" or name == "claude":
        return AnthropicProvider(
            api_key=ANTHROPIC_API_KEY,
            default_model=ANTHROPIC_MODEL
        )
    elif name == "ollama":
        return OllamaProvider(
            base_url=OLLAMA_BASE_URL,
            default_model=OLLAMA_MODEL
        )
    elif name == "groq":
        return GroqProvider(
            api_key=GROQ_API_KEY,
            default_model=GROQ_MODEL
        )
    elif name == "openrouter":
        return OpenRouterProvider(
            api_key=OPENROUTER_API_KEY,
            default_model=OPENROUTER_MODEL
        )
    else:
        raise ValueError(f"Unknown provider: {name}")


def list_providers() -> list[str]:
    """List available providers."""
    return ["openai", "gemini", "anthropic", "ollama", "groq", "openrouter"]


class BaseProvider:
    """Base class for AI providers."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self._client = None

    @property
    def name(self) -> str:
        return self.__class__.__name__.replace("Provider", "").lower()

    @property
    def is_available(self) -> bool:
        """Check if this provider is configured."""
        return bool(self.api_key or self.base_url)

    def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate a chat completion."""
        raise NotImplementedError

    def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Generate a streaming chat completion."""
        raise NotImplementedError


class OpenAIProvider(BaseProvider):
    """OpenAI GPT provider."""

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        return self._client

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        response = self.client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class GeminiProvider(BaseProvider):
    """Google Gemini provider."""

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _format_messages(self, messages: list[dict], system_prompt: Optional[str] = None) -> str:
        """Convert messages to Gemini format."""
        parts = []
        if system_prompt:
            parts.append(system_prompt + "\n\n")

        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            parts.append(f"{role}: {msg['content']}\n\n")

        return "".join(parts)

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model
        prompt = self._format_messages(messages, system_prompt)

        response = self.client.models.generate_content(
            model=model,
            contents=prompt
        )
        return response.text

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model
        prompt = self._format_messages(messages, system_prompt)

        response = self.client.models.generate_content_stream(
            model=model,
            contents=prompt
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider."""

    @property
    def client(self):
        if self._client is None:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
        return self._client

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model

        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model

        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": messages,
            "stream": True
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text


class OllamaProvider(BaseProvider):
    """Ollama local models provider."""

    def __init__(self, base_url: Optional[str] = None, default_model: str = "llama3"):
        super().__init__(base_url=base_url or "http://localhost:11434", default_model=default_model)

    @property
    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            import requests
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False

    @property
    def client(self):
        if self._client is None:
            from ollama import Client
            self._client = Client(host=self.base_url)
        return self._client

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        response = self.client.chat(model=model, messages=messages)
        return response["message"]["content"]

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        stream = self.client.chat(model=model, messages=messages, stream=True)

        for chunk in stream:
            if chunk["message"]["content"]:
                yield chunk["message"]["content"]


class GroqProvider(BaseProvider):
    """Groq fast inference provider."""

    @property
    def client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
        return self._client

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        response = self.client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class OpenRouterProvider(BaseProvider):
    """OpenRouter multi-model provider."""

    def __init__(self, api_key: Optional[str] = None, default_model: str = "anthropic/claude-3.5-sonnet"):
        super().__init__(api_key=api_key, default_model=default_model)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1"
            )
        return self._client

    def chat(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        response = self.client.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content

    def chat_stream(self, messages: list[dict], model: Optional[str] = None, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        model = model or self.default_model

        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        stream = self.client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# Convenience functions

def chat_completion(
    messages: list[dict],
    provider: str = "openai",
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    stream: bool = False
) -> str | Generator[str, None, None]:
    """
    Unified chat completion across all providers.

    Args:
        messages: List of message dicts with 'role' and 'content'
        provider: Provider name (openai, gemini, anthropic, ollama, groq, openrouter)
        model: Model name (uses provider default if not specified)
        system_prompt: System prompt to prepend
        stream: Whether to stream the response

    Returns:
        Response string, or generator if streaming
    """
    p = get_provider(provider)

    if not p.is_available:
        raise ValueError(f"Provider '{provider}' is not configured. Check your API key in .env")

    if stream:
        return p.chat_stream(messages, model=model, system_prompt=system_prompt)
    else:
        return p.chat(messages, model=model, system_prompt=system_prompt)


def available_providers() -> list[dict]:
    """List available (configured) providers."""
    result = []
    for name in list_providers():
        try:
            p = get_provider(name)
            result.append({
                "name": name,
                "available": p.is_available,
                "default_model": p.default_model
            })
        except:
            result.append({
                "name": name,
                "available": False,
                "default_model": ""
            })
    return result
