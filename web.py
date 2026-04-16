"""
Aetherion AI Web Interface

Flask-based web UI with streaming chat, similar to Gemini AI Studio.
"""

import json
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from config import SYSTEM_PROMPT, DEFAULT_PROVIDER, VAULT_PATH, OBSIDIAN_VAULT_NAME
from search import search as vault_search
from generate import (
    get_context_only, chat_with_context_stream, chat_with_context,
    multi_query_context, compress_context
)
from costs import estimate_chat_cost, format_cost, get_model_for_provider, count_tokens
from embeddings import get_stats

app = Flask(__name__)
CORS(app)

# In-memory session storage (use Redis/DB for production)
sessions = {}


@app.route("/")
def index():
    """Main chat interface."""
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    """Get vault statistics."""
    stats = get_stats()
    return jsonify(stats)


@app.route("/api/providers")
def api_providers():
    """List available providers."""
    from providers import available_providers
    return jsonify(available_providers())


@app.route("/api/search", methods=["POST"])
def api_search():
    """Search the vault."""
    data = request.json
    query = data.get("query", "")
    limit = data.get("limit", 10)

    results = vault_search(query, n_results=limit)

    # Format for frontend
    formatted = []
    for r in results:
        formatted.append({
            "path": r["file_path"],
            "header": r.get("header", ""),
            "content": r["content"][:300] + "..." if len(r["content"]) > 300 else r["content"],
            "score": round(r["score"] * 100, 1)
        })

    return jsonify({"results": formatted})


@app.route("/api/sources", methods=["POST"])
def api_sources():
    """Get context sources for a query."""
    data = request.json
    query = data.get("query", "")
    limit = data.get("limit", 20)
    deep = data.get("deep", False)

    if deep:
        sources = multi_query_context(query, n_results=limit)
        sources = compress_context(sources)
    else:
        sources = get_context_only(query, n_results=limit)

    # Format for frontend
    formatted = []
    for s in sources:
        formatted.append({
            "path": s.get("path", s.get("file_path", "")),
            "block": s.get("block", ""),
            "header": s.get("header", ""),
            "content": s.get("content", "")[:200],
            "score": round(s.get("score", 0) * 100, 1)
        })

    return jsonify({"sources": formatted})


@app.route("/api/estimate", methods=["POST"])
def api_estimate():
    """Estimate cost for a message."""
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])
    sources = data.get("sources", [])
    provider = data.get("provider", DEFAULT_PROVIDER)

    context_text = "\n".join([s.get("content", "") for s in sources])
    model = get_model_for_provider(provider)

    cost = estimate_chat_cost(
        messages=history + [{"role": "user", "content": message}],
        system_prompt=SYSTEM_PROMPT,
        context=context_text,
        model=model
    )

    return jsonify({
        "input_tokens": cost["input_tokens"],
        "output_tokens": cost["output_tokens"],
        "total_cost": cost["total_cost"],
        "is_free": cost["is_free"],
        "formatted": format_cost(cost).replace("[green]", "").replace("[/green]", "")
    })


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Non-streaming chat endpoint."""
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])
    sources = data.get("sources", [])
    provider = data.get("provider", DEFAULT_PROVIDER)

    # Convert sources to expected format
    formatted_sources = []
    for s in sources:
        formatted_sources.append({
            "path": s.get("path", ""),
            "block": s.get("block", s.get("path", "")),
            "header": s.get("header", ""),
            "score": s.get("score", 0) / 100,
            "content": s.get("content", "")
        })

    response = chat_with_context(
        message,
        sources=formatted_sources,
        history=history,
        provider=provider,
        system_prompt=SYSTEM_PROMPT
    )

    return jsonify({"response": response})


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """Streaming chat endpoint using Server-Sent Events."""
    data = request.json
    message = data.get("message", "")
    history = data.get("history", [])
    sources = data.get("sources", [])
    provider = data.get("provider", DEFAULT_PROVIDER)

    # Convert sources to expected format
    formatted_sources = []
    for s in sources:
        formatted_sources.append({
            "path": s.get("path", ""),
            "block": s.get("block", s.get("path", "")),
            "header": s.get("header", ""),
            "score": s.get("score", 0) / 100,
            "content": s.get("content", "")
        })

    def generate():
        try:
            stream = chat_with_context_stream(
                message,
                sources=formatted_sources,
                history=history,
                provider=provider,
                system_prompt=SYSTEM_PROMPT
            )

            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/note/<path:file_path>")
def api_note(file_path):
    """Get full content of a note."""
    full_path = VAULT_PATH / file_path

    if not full_path.exists():
        return jsonify({"error": "File not found"}), 404

    content = full_path.read_text(encoding="utf-8")

    return jsonify({
        "path": file_path,
        "content": content,
        "obsidian_url": f"obsidian://open?vault={OBSIDIAN_VAULT_NAME}&file={file_path}"
    })


@app.route("/api/tokens", methods=["POST"])
def api_count_tokens():
    """Count tokens in text and calculate cost."""
    data = request.json
    text = data.get("text", "")
    model = data.get("model", "gpt-4o")
    token_type = data.get("type", "output")  # "input" or "output"

    tokens = count_tokens(text, model)

    # Get pricing
    from costs import PRICING, DEFAULT_PRICING
    pricing = PRICING.get(model, DEFAULT_PRICING)

    if token_type == "output":
        cost = (tokens / 1_000_000) * pricing["output"]
    else:
        cost = (tokens / 1_000_000) * pricing["input"]

    return jsonify({
        "tokens": tokens,
        "cost": cost,
        "is_free": pricing["input"] == 0 and pricing["output"] == 0
    })


# =============================================================================
# FEATURE ENDPOINTS
# =============================================================================

@app.route("/api/auto-link", methods=["POST"])
def api_auto_link():
    """Auto-link entity names in text."""
    from features import auto_link_text
    data = request.json
    text = data.get("text", "")
    linked = auto_link_text(text)
    return jsonify({"text": linked})


@app.route("/api/characters")
def api_characters():
    """Get list of characters for voice mode."""
    from features import get_characters
    characters = get_characters()
    return jsonify({"characters": characters})


@app.route("/api/character/<name>")
def api_character(name):
    """Get character details for voice mode."""
    from features import get_character_context, build_character_prompt
    char_data = get_character_context(name)
    if not char_data:
        return jsonify({"error": "Character not found"}), 404

    prompt = build_character_prompt(name, char_data)
    return jsonify({
        "name": name,
        "content": char_data['content'][:500],
        "has_personality": char_data.get('personality_prompt') is not None,
        "prompt": prompt
    })


@app.route("/api/chat/character", methods=["POST"])
def api_chat_character():
    """Chat as a specific character (streaming)."""
    from features import get_character_context, build_character_prompt
    from generate import chat_with_context_stream

    data = request.json
    message = data.get("message", "")
    character = data.get("character", "")
    history = data.get("history", [])
    sources = data.get("sources", [])
    provider = data.get("provider", DEFAULT_PROVIDER)

    # Get character context
    char_data = get_character_context(character)
    if not char_data:
        return jsonify({"error": "Character not found"}), 404

    # Build character prompt
    char_prompt = build_character_prompt(character, char_data)

    # Convert sources
    formatted_sources = []
    for s in sources:
        formatted_sources.append({
            "path": s.get("path", ""),
            "block": s.get("block", s.get("path", "")),
            "header": s.get("header", ""),
            "score": s.get("score", 0) / 100,
            "content": s.get("content", "")
        })

    def generate():
        try:
            stream = chat_with_context_stream(
                message,
                sources=formatted_sources,
                history=history,
                provider=provider,
                system_prompt=char_prompt
            )

            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/graph")
def api_graph():
    """Get relationship graph data."""
    from features import build_relationship_graph
    graph = build_relationship_graph()
    return jsonify(graph)


@app.route("/api/graph/sections/<path:file_path>")
def api_graph_sections(file_path):
    """Get sections within a file for graph drill-down."""
    from features import extract_sections_from_file
    full_path = VAULT_PATH / file_path

    if not full_path.exists():
        return jsonify({"error": "File not found"}), 404

    sections = extract_sections_from_file(full_path)
    return jsonify({
        "file": file_path,
        "sections": sections
    })


@app.route("/graph")
def graph_view():
    """Relationship graph visualization page."""
    return render_template("graph.html")


@app.route("/api/session-recap", methods=["POST"])
def api_session_recap():
    """Generate a session recap from notes."""
    from features import format_session_recap_prompt, auto_link_text
    from generate import chat_with_context_stream

    data = request.json
    raw_notes = data.get("notes", "")
    session_number = data.get("session_number")
    provider = data.get("provider", DEFAULT_PROVIDER)

    prompt = format_session_recap_prompt(raw_notes, session_number)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a D&D session scribe. Format session notes into polished recaps."
            )

            full_response = ""
            for chunk in stream:
                full_response += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            # Auto-link the final response
            linked = auto_link_text(full_response)
            yield f"data: {json.dumps({'done': True, 'linked': linked})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/consistency/entities")
def api_consistency_entities():
    """Get major entities for consistency checking."""
    from features import get_major_entities
    entities = get_major_entities(min_mentions=2)
    return jsonify({"entities": entities[:50]})  # Top 50


@app.route("/api/consistency/check", methods=["POST"])
def api_consistency_check():
    """Check consistency for an entity."""
    from features import extract_entity_descriptions, build_consistency_prompt
    from generate import chat_with_context_stream

    data = request.json
    entity = data.get("entity", "")
    provider = data.get("provider", DEFAULT_PROVIDER)

    mentions = extract_entity_descriptions(entity)

    if not mentions:
        return jsonify({"error": "No mentions found"}), 404

    prompt = build_consistency_prompt(entity, mentions)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a lore consistency checker. Analyze excerpts for contradictions."
            )

            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"

            yield f"data: {json.dumps({'done': True, 'mention_count': len(mentions)})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )


@app.route("/api/vault/folders")
def api_vault_folders():
    """Get vault folders for save dialog."""
    from features import get_vault_folders
    folders = get_vault_folders()
    return jsonify({"folders": folders})


@app.route("/api/vault/save", methods=["POST"])
def api_vault_save():
    """Save content to vault as new note."""
    from features import save_to_vault
    data = request.json
    content = data.get("content", "")
    filename = data.get("filename", "")
    folder = data.get("folder", "Notes")
    add_links = data.get("add_links", True)

    result = save_to_vault(content, filename, folder, add_links)
    return jsonify(result)


if __name__ == "__main__":
    print("\n  Aetherion AI Web Interface")
    print("  http://localhost:5000\n")
    app.run(debug=True, port=5000, threaded=True)
