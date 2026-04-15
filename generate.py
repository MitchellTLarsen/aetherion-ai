"""AI generation using Gemini and GPT with streaming support."""
from typing import Optional, Generator
import json

from google import genai
from openai import OpenAI

from config import (
    OPENAI_API_KEY, GEMINI_API_KEY, GEMINI_MODEL, GPT_MODEL,
    VAULT_PATH, SYSTEM_PROMPT, CHAT_HISTORY_PATH
)
from search import search, get_full_note

# Initialize Gemini client
_gemini_client = None


def get_gemini_client():
    """Get Gemini client (singleton)."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def get_openai_client() -> OpenAI:
    """Get OpenAI client."""
    return OpenAI(api_key=OPENAI_API_KEY)


def build_context(query: str, n_results: int = 5) -> tuple[str, list[dict]]:
    """
    Build context from relevant vault content.

    Returns:
        Tuple of (context_string, list of source references)
    """
    results = search(query, n_results=n_results)

    if not results:
        return "", []

    context_parts = ["## Relevant Lore from the Vault\n"]
    sources = []

    for r in results:
        # Build block reference path
        block_ref = r['file_path']
        if r["header"]:
            # Create obsidian-style block link
            header_slug = r["header"].lower().replace(" ", "-")
            block_ref = f"{r['file_path']}#{header_slug}"

        context_parts.append(f"### From: {block_ref}")
        if r["header"]:
            context_parts.append(f"Section: {r['header']}")
        context_parts.append(r["content"])
        context_parts.append("")

        sources.append({
            "path": r["file_path"],
            "block": block_ref,
            "header": r["header"],
            "score": r["score"],
            "content": r["content"]
        })

    return "\n".join(context_parts), sources


def get_context_only(query: str, n_results: int = 5) -> list[dict]:
    """Get context sources without building the full context string."""
    _, sources = build_context(query, n_results=n_results)
    return sources


def multi_query_context(query: str, n_results: int = 20) -> list[dict]:
    """
    Break complex queries into sub-queries for better retrieval.
    Uses LLM to generate related search queries.
    """
    client = get_openai_client()

    # Generate sub-queries
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=[{
            "role": "user",
            "content": f"""Given this question about a fantasy world, generate 3 different search queries that would help find relevant information. Return only the queries, one per line, no numbering.

Question: {query}"""
        }]
    )

    sub_queries = response.choices[0].message.content.strip().split("\n")
    sub_queries = [q.strip() for q in sub_queries if q.strip()][:3]
    sub_queries.insert(0, query)  # Include original query

    # Search with each query and combine results
    all_sources = {}
    for q in sub_queries:
        sources = get_context_only(q, n_results=n_results // len(sub_queries))
        for src in sources:
            key = src["block"]
            if key not in all_sources or src["score"] > all_sources[key]["score"]:
                all_sources[key] = src

    # Sort by score and return
    return sorted(all_sources.values(), key=lambda x: x["score"], reverse=True)[:n_results]


def compress_context(sources: list[dict], max_chars: int = 8000) -> list[dict]:
    """
    Compress context by summarizing if it exceeds max length.
    Keeps highest scoring sources and summarizes lower ones.
    """
    total_chars = sum(len(s.get("content", "")) for s in sources)

    if total_chars <= max_chars:
        return sources

    # Keep top sources as-is, summarize the rest
    compressed = []
    current_chars = 0
    needs_summary = []

    for src in sources:
        content_len = len(src.get("content", ""))
        if current_chars + content_len <= max_chars * 0.7:
            compressed.append(src)
            current_chars += content_len
        else:
            needs_summary.append(src)

    # Summarize remaining sources
    if needs_summary:
        client = get_openai_client()
        combined = "\n\n".join([f"From {s['block']}:\n{s['content'][:500]}" for s in needs_summary[:5]])

        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{
                "role": "user",
                "content": f"Briefly summarize the key facts from these excerpts (2-3 sentences each):\n\n{combined}"
            }]
        )

        summary = response.choices[0].message.content
        compressed.append({
            "path": "summary",
            "block": "compressed-context",
            "header": "Summary of additional sources",
            "score": 0.5,
            "content": summary
        })

    return compressed


def chat_with_context(
    message: str,
    sources: list[dict],
    history: Optional[list[dict]] = None,
    provider: str = "gemini",
    system_prompt: Optional[str] = None
) -> str:
    """
    Chat with pre-built context (for confirm-before-send flow).
    """
    prompt = system_prompt or SYSTEM_PROMPT

    # Build context string from sources
    context_parts = ["## Relevant Lore from the Vault\n"]
    for src in sources:
        context_parts.append(f"### From: {src['block']}")
        if src.get("header"):
            context_parts.append(f"Section: {src['header']}")
        context_parts.append(src.get("content", ""))
        context_parts.append("")
    vault_context = "\n".join(context_parts) if sources else ""

    if provider == "gemini":
        client = get_gemini_client()

        full_prompt = f"{prompt}\n\n{vault_context}\n\n"

        if history:
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                full_prompt += f"{role}: {msg['content']}\n\n"

        full_prompt += f"User: {message}\n\nAssistant:"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt
        )
        return response.text

    else:
        client = get_openai_client()

        messages = [{"role": "system", "content": f"{prompt}\n\n{vault_context}"}]

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages
        )

        return response.choices[0].message.content


def chat_with_context_stream(
    message: str,
    sources: list[dict],
    history: Optional[list[dict]] = None,
    provider: str = "gpt",
    system_prompt: Optional[str] = None
) -> Generator[str, None, None]:
    """
    Chat with streaming response.
    Yields chunks of text as they're generated.
    """
    prompt = system_prompt or SYSTEM_PROMPT

    # Build context string from sources
    context_parts = ["## Relevant Lore from the Vault\n"]
    for src in sources:
        context_parts.append(f"### From: {src['block']}")
        if src.get("header"):
            context_parts.append(f"Section: {src['header']}")
        context_parts.append(src.get("content", ""))
        context_parts.append("")
    vault_context = "\n".join(context_parts) if sources else ""

    if provider == "gemini":
        # Gemini streaming
        client = get_gemini_client()

        full_prompt = f"{prompt}\n\n{vault_context}\n\n"

        if history:
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                full_prompt += f"{role}: {msg['content']}\n\n"

        full_prompt += f"User: {message}\n\nAssistant:"

        response = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=full_prompt
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    else:
        # OpenAI streaming
        client = get_openai_client()

        messages = [{"role": "system", "content": f"{prompt}\n\n{vault_context}"}]

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": message})

        stream = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            stream=True
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# Chat history management

def save_chat_history(session_name: str, history: list[dict], sources_log: list[list[dict]] = None):
    """Save chat history to a file."""
    filepath = CHAT_HISTORY_PATH / f"{session_name}.json"
    data = {
        "history": history,
        "sources_log": sources_log or []
    }
    filepath.write_text(json.dumps(data, indent=2))


def load_chat_history(session_name: str) -> tuple[list[dict], list[list[dict]]]:
    """Load chat history from a file."""
    filepath = CHAT_HISTORY_PATH / f"{session_name}.json"
    if filepath.exists():
        data = json.loads(filepath.read_text())
        return data.get("history", []), data.get("sources_log", [])
    return [], []


def list_chat_sessions() -> list[str]:
    """List available chat sessions."""
    return [f.stem for f in CHAT_HISTORY_PATH.glob("*.json")]


def delete_chat_session(session_name: str) -> bool:
    """Delete a chat session."""
    filepath = CHAT_HISTORY_PATH / f"{session_name}.json"
    if filepath.exists():
        filepath.unlink()
        return True
    return False


# Legacy functions for backwards compatibility

def generate_with_gemini(
    prompt: str,
    context: Optional[str] = None,
    use_vault_context: bool = True,
    n_context: int = 5,
    return_sources: bool = False
) -> str | tuple[str, list[dict]]:
    """Generate content using Gemini Flash."""
    client = get_gemini_client()

    vault_context = ""
    sources = []
    if use_vault_context:
        vault_context, sources = build_context(prompt, n_results=n_context)

    full_prompt = f"{SYSTEM_PROMPT}\n\n"

    if vault_context:
        full_prompt += f"{vault_context}\n\n"

    if context:
        full_prompt += f"## Additional Context\n{context}\n\n"

    full_prompt += f"## Request\n{prompt}"

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt
    )

    if return_sources:
        return response.text, sources
    return response.text


def generate_with_gpt(
    prompt: str,
    context: Optional[str] = None,
    use_vault_context: bool = True,
    n_context: int = 5,
    model: str = GPT_MODEL,
    return_sources: bool = False
) -> str | tuple[str, list[dict]]:
    """Generate content using GPT."""
    client = get_openai_client()

    vault_context = ""
    sources = []
    if use_vault_context:
        vault_context, sources = build_context(prompt, n_results=n_context)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_content = ""
    if vault_context:
        user_content += f"{vault_context}\n\n"
    if context:
        user_content += f"## Additional Context\n{context}\n\n"
    user_content += f"## Request\n{prompt}"

    messages.append({"role": "user", "content": user_content})

    response = client.chat.completions.create(
        model=model,
        messages=messages
    )

    if return_sources:
        return response.choices[0].message.content, sources
    return response.choices[0].message.content


def expand_note(
    file_path: str,
    aspect: Optional[str] = None,
    provider: str = "gemini"
) -> str:
    """Expand on an existing note."""
    content = get_full_note(file_path)
    if not content:
        return f"Error: Could not find note at {file_path}"

    prompt = f"Expand on this content from the vault:\n\n{content}\n\n"

    if aspect:
        prompt += f"Focus specifically on: {aspect}\n"
    else:
        prompt += "Add more depth and detail while maintaining consistency with the established lore.\n"

    prompt += "Generate new content that enriches this entry."

    if provider == "gemini":
        return generate_with_gemini(prompt)
    else:
        return generate_with_gpt(prompt)


def generate_encounter(
    location: str,
    party_level: int = 5,
    difficulty: str = "medium",
    themes: Optional[list[str]] = None,
    provider: str = "gemini"
) -> str:
    """Generate a D&D encounter for a location."""
    prompt = f"""Create a D&D 5e encounter for the following:

Location: {location}
Party Level: {party_level}
Difficulty: {difficulty}
{"Themes: " + ", ".join(themes) if themes else ""}

Include:
1. Encounter description and setup
2. Enemy stat blocks or references
3. Tactical considerations
4. Possible treasure/rewards
5. Hooks to other locations or NPCs in the world
"""

    if provider == "gemini":
        return generate_with_gemini(prompt, n_context=8)
    else:
        return generate_with_gpt(prompt, n_context=8)


def generate_npc(
    location: str,
    role: Optional[str] = None,
    provider: str = "gemini"
) -> str:
    """Generate an NPC for a location."""
    prompt = f"""Create a detailed NPC for the world of Aetherion.

Location: {location}
{"Role: " + role if role else ""}

Include:
1. Name and physical description
2. Personality and mannerisms
3. Background and motivations
4. Connections to the world
5. Useful information they might have
6. Potential quest hooks
"""

    if provider == "gemini":
        return generate_with_gemini(prompt, n_context=8)
    else:
        return generate_with_gpt(prompt, n_context=8)


def chat(
    message: str,
    history: Optional[list[dict]] = None,
    provider: str = "gemini",
    return_sources: bool = False
) -> str | tuple[str, list[dict]]:
    """Chat about the world with context awareness."""
    vault_context, sources = build_context(message, n_results=5)

    if provider == "gemini":
        client = get_gemini_client()

        full_prompt = f"{SYSTEM_PROMPT}\n\n{vault_context}\n\n"

        if history:
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                full_prompt += f"{role}: {msg['content']}\n\n"

        full_prompt += f"User: {message}\n\nAssistant:"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt
        )
        result = response.text

    else:
        client = get_openai_client()

        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{vault_context}"}]

        if history:
            messages.extend(history[-10:])

        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages
        )

        result = response.choices[0].message.content

    if return_sources:
        return result, sources
    return result
