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


# =============================================================================
# CAMPAIGN MANAGEMENT ENDPOINTS
# =============================================================================

@app.route("/worldbuilding")
def worldbuilding_view():
    """Worldbuilding hub dashboard."""
    return render_template("worldbuilding.html")


@app.route("/api/campaign/overview")
def api_campaign_overview():
    """Get campaign overview stats."""
    from features import get_campaign_overview
    return jsonify(get_campaign_overview())


@app.route("/api/campaign/npc-card/<name>")
def api_npc_card(name):
    """Get NPC data for card generation."""
    from features import get_npc_for_card
    npc = get_npc_for_card(name)
    if not npc:
        return jsonify({"error": "NPC not found"}), 404
    return jsonify(npc)


@app.route("/api/campaign/npc-card/generate", methods=["POST"])
def api_generate_npc_card():
    """Generate NPC quick card using AI."""
    from features import get_npc_for_card, build_npc_card_prompt
    from generate import chat_with_context_stream

    data = request.json
    name = data.get("name", "")
    provider = data.get("provider", DEFAULT_PROVIDER)

    npc = get_npc_for_card(name)
    if not npc:
        return jsonify({"error": "NPC not found"}), 404

    prompt = build_npc_card_prompt(npc["name"], npc["content"])

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a D&D game master assistant. Create concise, useful NPC reference cards."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


@app.route("/api/campaign/names")
def api_naming_patterns():
    """Get naming patterns by culture."""
    from features import analyze_naming_patterns
    return jsonify(analyze_naming_patterns())


@app.route("/api/campaign/names/generate", methods=["POST"])
def api_generate_names():
    """Generate names for a culture."""
    from features import analyze_naming_patterns, build_name_generator_prompt
    from generate import chat_with_context_stream

    data = request.json
    culture = data.get("culture", "")
    count = data.get("count", 10)
    provider = data.get("provider", DEFAULT_PROVIDER)

    patterns = analyze_naming_patterns()
    if culture not in patterns:
        return jsonify({"error": "Culture not found"}), 404

    prompt = build_name_generator_prompt(culture, patterns[culture], count)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a fantasy name generator. Generate names that match the given cultural style."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


@app.route("/api/campaign/timeline")
def api_timeline():
    """Get timeline events."""
    from features import extract_timeline_events
    return jsonify({"events": extract_timeline_events()})


@app.route("/api/campaign/factions")
def api_factions():
    """Get faction relationships."""
    from features import extract_faction_relationships
    return jsonify(extract_faction_relationships())


@app.route("/api/campaign/threads")
def api_threads():
    """Get unresolved plot threads."""
    from features import find_unresolved_threads
    return jsonify({"threads": find_unresolved_threads()})


@app.route("/api/campaign/gaps")
def api_lore_gaps():
    """Get lore gaps and missing information."""
    from features import find_lore_gaps, find_broken_links
    return jsonify({
        "gaps": find_lore_gaps(),
        "broken_links": find_broken_links()
    })


@app.route("/api/campaign/expand", methods=["POST"])
def api_expand_description():
    """Expand brief notes into vivid prose."""
    from features import build_description_prompt
    from generate import chat_with_context_stream

    data = request.json
    notes = data.get("notes", "")
    context = data.get("context", "")
    provider = data.get("provider", DEFAULT_PROVIDER)

    prompt = build_description_prompt(notes, context)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a fantasy writer. Expand notes into vivid, immersive prose."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


@app.route("/api/campaign/sensory", methods=["POST"])
def api_sensory_enrich():
    """Add sensory details to a description."""
    from features import build_sensory_prompt
    from generate import chat_with_context_stream

    data = request.json
    description = data.get("description", "")
    provider = data.get("provider", DEFAULT_PROVIDER)

    prompt = build_sensory_prompt(description)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a fantasy writer specializing in immersive descriptions."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


# =============================================================================
# SESSION MANAGEMENT ENDPOINTS
# =============================================================================

@app.route("/campaign")
def campaign_view():
    """Campaign Manager dashboard."""
    return render_template("campaign.html")


@app.route("/api/sessions")
def api_sessions():
    """Get all sessions."""
    from features import get_all_sessions
    return jsonify({"sessions": get_all_sessions()})


@app.route("/api/sessions/<path:session_path>")
def api_session_detail(session_path):
    """Get session content."""
    from features import get_session_content
    session = get_session_content(session_path)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@app.route("/api/sessions/create", methods=["POST"])
def api_create_session():
    """Create new session note."""
    from features import create_session_note
    data = request.json
    session_number = data.get("session_number", 1)
    title = data.get("title", "")
    date = data.get("date", "")
    result = create_session_note(session_number, title, date)
    return jsonify(result)


@app.route("/api/sessions/previously-on", methods=["POST"])
def api_previously_on():
    """Generate 'Previously On...' recap."""
    from features import get_all_sessions, get_session_content, build_previously_on_prompt
    from generate import chat_with_context_stream

    data = request.json
    session_count = data.get("session_count", 3)
    provider = data.get("provider", DEFAULT_PROVIDER)

    sessions = get_all_sessions()[:session_count]
    session_data = []
    for s in sessions:
        content = get_session_content(s["path"])
        if content:
            session_data.append({
                "title": s["title"],
                "content": content["content"]
            })

    if not session_data:
        return jsonify({"error": "No sessions found"}), 404

    prompt = build_previously_on_prompt(session_data)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a dramatic narrator creating session recaps."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


@app.route("/api/sessions/prep", methods=["POST"])
def api_session_prep():
    """Generate session prep guide."""
    from features import (
        get_all_sessions, get_session_content, get_all_quests,
        get_party_members, build_session_prep_prompt
    )
    from generate import chat_with_context_stream

    data = request.json
    provider = data.get("provider", DEFAULT_PROVIDER)

    # Gather context
    sessions = get_all_sessions()[:3]
    session_text = ""
    for s in sessions:
        content = get_session_content(s["path"])
        if content:
            session_text += f"\n### {s['title']}\n{content['content'][:1500]}"

    quests = get_all_quests()
    quest_text = "\n".join([f"- {q['name']} ({q['status']}): {q['summary']}" for q in quests[:10]])

    party = get_party_members()
    party_text = "\n".join([f"- {p['name']}: Level {p.get('level', '?')} {p.get('class', 'Unknown')}" for p in party])

    # NPCs would come from encounter log
    from features import get_npc_encounters
    npcs = get_npc_encounters()[:10]
    npc_text = "\n".join([f"- {n['name']} ({n['disposition']})" for n in npcs])

    prompt = build_session_prep_prompt(session_text, quest_text, npc_text, party_text)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a D&D session planning assistant."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


# =============================================================================
# QUEST MANAGEMENT ENDPOINTS
# =============================================================================

@app.route("/api/quests")
def api_quests():
    """Get all quests."""
    from features import get_all_quests
    return jsonify({"quests": get_all_quests()})


@app.route("/api/quests/create", methods=["POST"])
def api_create_quest():
    """Create new quest."""
    from features import create_quest_note
    data = request.json
    result = create_quest_note(data)
    return jsonify(result)


# =============================================================================
# PARTY MANAGEMENT ENDPOINTS
# =============================================================================

@app.route("/api/party")
def api_party():
    """Get party members."""
    from features import get_party_members
    return jsonify({"members": get_party_members()})


@app.route("/api/party/<name>/update", methods=["POST"])
def api_update_party_member(name):
    """Update party member stats."""
    from features import update_party_member
    data = request.json
    result = update_party_member(name, data)
    return jsonify(result)


# =============================================================================
# NPC ENCOUNTER TRACKING
# =============================================================================

@app.route("/api/npcs/encounters")
def api_npc_encounters():
    """Get NPC encounter history."""
    from features import get_npc_encounters
    return jsonify({"encounters": get_npc_encounters()})


# =============================================================================
# CALENDAR ENDPOINTS
# =============================================================================

@app.route("/api/calendar")
def api_calendar():
    """Get calendar events."""
    from features import get_calendar_events, get_campaign_calendar_state
    return jsonify({
        "events": get_calendar_events(),
        "current": get_campaign_calendar_state()
    })


# =============================================================================
# ENCOUNTER & LOOT GENERATORS
# =============================================================================

@app.route("/api/encounter/generate", methods=["POST"])
def api_generate_encounter():
    """Generate an encounter."""
    from features import build_encounter_prompt, get_party_members
    from generate import chat_with_context_stream

    data = request.json
    setting = data.get("setting", "")
    difficulty = data.get("difficulty", "medium")
    encounter_type = data.get("type", "combat")
    provider = data.get("provider", DEFAULT_PROVIDER)

    party = get_party_members()
    party_text = "\n".join([
        f"- {p['name']}: Level {p.get('level', '?')} {p.get('class', 'Unknown')}"
        for p in party
    ])

    prompt = build_encounter_prompt(party_text, setting, difficulty, encounter_type)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a D&D encounter designer."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


@app.route("/api/loot/generate", methods=["POST"])
def api_generate_loot():
    """Generate loot for an encounter."""
    from features import build_loot_prompt
    from generate import chat_with_context_stream

    data = request.json
    level = data.get("level", 5)
    encounter_type = data.get("type", "combat")
    setting = data.get("setting", "")
    provider = data.get("provider", DEFAULT_PROVIDER)

    prompt = build_loot_prompt(level, encounter_type, setting)

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt,
                sources=[],
                history=[],
                provider=provider,
                system_prompt="You are a D&D loot generator."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream"
    )


# =============================================================================
# RANDOM TABLES
# =============================================================================

@app.route("/api/tables")
def api_random_tables():
    """Get available random tables."""
    from features import get_random_tables
    return jsonify({"tables": get_random_tables()})


# =============================================================================
# CAMPAIGN STATE PERSISTENCE
# =============================================================================

@app.route("/api/campaign/state")
def api_campaign_state():
    """Get full campaign state."""
    from features import get_campaign_data
    return jsonify(get_campaign_data())


@app.route("/api/campaign/state", methods=["POST"])
def api_update_campaign_state():
    """Update campaign state."""
    from features import update_campaign_data
    data = request.json
    result = update_campaign_data(data)
    return jsonify(result)


@app.route("/api/campaign/party/<name>/state", methods=["POST"])
def api_update_party_state(name):
    """Update party member's live state (HP, conditions)."""
    from features import update_party_state
    data = request.json
    result = update_party_state(name, data)
    return jsonify(result)


@app.route("/api/campaign/quest/<name>/state", methods=["POST"])
def api_update_quest_state(name):
    """Update quest status."""
    from features import update_quest_state
    data = request.json
    result = update_quest_state(name, data)
    return jsonify(result)


@app.route("/api/campaign/calendar/advance", methods=["POST"])
def api_advance_calendar():
    """Advance in-world calendar."""
    from features import advance_calendar
    data = request.json
    days = data.get("days", 1)
    result = advance_calendar(days)
    return jsonify(result)


# =============================================================================
# INITIATIVE TRACKER
# =============================================================================

@app.route("/api/combat/start", methods=["POST"])
def api_start_combat():
    """Start a new combat encounter."""
    from features import start_combat
    return jsonify(start_combat())


@app.route("/api/combat/end", methods=["POST"])
def api_end_combat():
    """End current combat."""
    from features import end_combat
    return jsonify(end_combat())


@app.route("/api/combat/combatant", methods=["POST"])
def api_add_combatant():
    """Add a combatant."""
    from features import add_combatant
    data = request.json
    result = add_combatant(
        name=data.get("name"),
        initiative=data.get("initiative", 0),
        hp=data.get("hp", 0),
        max_hp=data.get("max_hp", 0),
        is_pc=data.get("is_pc", False),
        group=data.get("group", "")
    )
    return jsonify(result)


@app.route("/api/combat/combatant/<combatant_id>", methods=["DELETE"])
def api_remove_combatant(combatant_id):
    """Remove a combatant."""
    from features import remove_combatant
    return jsonify(remove_combatant(combatant_id))


@app.route("/api/combat/combatant/<combatant_id>", methods=["PATCH"])
def api_update_combatant(combatant_id):
    """Update a combatant."""
    from features import update_combatant
    return jsonify(update_combatant(combatant_id, request.json))


@app.route("/api/combat/next-turn", methods=["POST"])
def api_next_turn():
    """Advance to next turn."""
    from features import next_turn
    return jsonify(next_turn())


@app.route("/api/combat/log", methods=["POST"])
def api_log_combat():
    """Log a combat action."""
    from features import log_combat_action
    data = request.json
    result = log_combat_action(
        actor=data.get("actor"),
        action=data.get("action"),
        target=data.get("target", ""),
        damage=data.get("damage", 0),
        notes=data.get("notes", "")
    )
    return jsonify(result)


# =============================================================================
# RESOURCE TRACKER
# =============================================================================

@app.route("/api/resources/<pc_name>")
def api_get_resources(pc_name):
    """Get PC resources."""
    from features import get_pc_resources
    return jsonify(get_pc_resources(pc_name))


@app.route("/api/resources/<pc_name>", methods=["POST"])
def api_update_resources(pc_name):
    """Update PC resources."""
    from features import update_pc_resources
    return jsonify(update_pc_resources(pc_name, request.json))


@app.route("/api/resources/<pc_name>/spell-slot", methods=["POST"])
def api_use_spell_slot(pc_name):
    """Use a spell slot."""
    from features import use_spell_slot
    data = request.json
    return jsonify(use_spell_slot(pc_name, data.get("level", 1)))


@app.route("/api/resources/<pc_name>/ability", methods=["POST"])
def api_use_ability(pc_name):
    """Use an ability."""
    from features import use_ability
    data = request.json
    return jsonify(use_ability(pc_name, data.get("ability")))


@app.route("/api/resources/long-rest", methods=["POST"])
def api_long_rest():
    """Long rest - restore all resources."""
    from features import long_rest_resources
    data = request.json
    return jsonify(long_rest_resources(data.get("pc_name", "")))


# =============================================================================
# INSPIRATION
# =============================================================================

@app.route("/api/inspiration/<pc_name>", methods=["POST"])
def api_toggle_inspiration(pc_name):
    """Toggle inspiration."""
    from features import toggle_inspiration
    data = request.json
    return jsonify(toggle_inspiration(pc_name, data.get("reason", "")))


# =============================================================================
# DOWNTIME
# =============================================================================

@app.route("/api/downtime", methods=["POST"])
def api_add_downtime():
    """Add downtime activity."""
    from features import add_downtime
    data = request.json
    return jsonify(add_downtime(
        pc_name=data.get("pc_name"),
        activity=data.get("activity"),
        days=data.get("days", 1),
        notes=data.get("notes", "")
    ))


@app.route("/api/downtime/<downtime_id>/complete", methods=["POST"])
def api_complete_downtime(downtime_id):
    """Complete a downtime activity."""
    from features import complete_downtime
    return jsonify(complete_downtime(downtime_id))


# =============================================================================
# PROGRESSION (XP/MILESTONES)
# =============================================================================

@app.route("/api/progression/xp", methods=["POST"])
def api_add_xp():
    """Add XP."""
    from features import add_xp
    data = request.json
    return jsonify(add_xp(data.get("amount", 0), data.get("reason", "")))


@app.route("/api/progression/level", methods=["POST"])
def api_set_level():
    """Set party level."""
    from features import set_party_level
    data = request.json
    return jsonify(set_party_level(data.get("level", 1)))


@app.route("/api/progression/milestone", methods=["POST"])
def api_add_milestone():
    """Add a milestone."""
    from features import add_milestone
    data = request.json
    return jsonify(add_milestone(data.get("name"), data.get("description", "")))


# =============================================================================
# RUMORS
# =============================================================================

@app.route("/api/rumors", methods=["POST"])
def api_add_rumor():
    """Add a rumor."""
    from features import add_rumor
    data = request.json
    return jsonify(add_rumor(
        text=data.get("text"),
        source=data.get("source", ""),
        status=data.get("status", "unknown")
    ))


@app.route("/api/rumors/<rumor_id>", methods=["PATCH"])
def api_update_rumor(rumor_id):
    """Update a rumor."""
    from features import update_rumor
    return jsonify(update_rumor(rumor_id, request.json))


# =============================================================================
# SECRETS
# =============================================================================

@app.route("/api/secrets", methods=["POST"])
def api_add_secret():
    """Add a secret."""
    from features import add_secret
    data = request.json
    return jsonify(add_secret(
        name=data.get("name"),
        description=data.get("description"),
        known_by=data.get("known_by", [])
    ))


@app.route("/api/secrets/<secret_id>/reveal", methods=["POST"])
def api_reveal_secret(secret_id):
    """Reveal a secret."""
    from features import reveal_secret
    data = request.json
    return jsonify(reveal_secret(secret_id, data.get("to_whom", [])))


# =============================================================================
# HANDOUTS
# =============================================================================

@app.route("/api/handouts", methods=["POST"])
def api_add_handout():
    """Add a handout."""
    from features import add_handout
    data = request.json
    return jsonify(add_handout(
        title=data.get("title"),
        content=data.get("content"),
        given_to=data.get("given_to", [])
    ))


# =============================================================================
# WEATHER
# =============================================================================

@app.route("/api/weather/generate", methods=["POST"])
def api_generate_weather():
    """Generate weather."""
    from features import build_weather_prompt, get_campaign_data
    from generate import chat_with_context_stream

    data = request.json
    campaign = get_campaign_data()
    prompt = build_weather_prompt(
        season=data.get("season", "summer"),
        region=data.get("region", "temperate"),
        previous=campaign.get("current_weather", "")
    )

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt, sources=[], history=[],
                provider=data.get("provider", "gemini"),
                system_prompt="You are a fantasy weather generator."
            )
            full = ""
            for chunk in stream:
                full += chunk
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            # Save the weather
            from features import save_weather
            save_weather(full)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# =============================================================================
# SHOP GENERATOR
# =============================================================================

@app.route("/api/shop/generate", methods=["POST"])
def api_generate_shop():
    """Generate shop inventory."""
    from features import build_shop_prompt
    from generate import chat_with_context_stream

    data = request.json
    prompt = build_shop_prompt(
        shop_type=data.get("shop_type", "general store"),
        settlement=data.get("settlement", "town"),
        level=data.get("level", 5),
        notes=data.get("notes", "")
    )

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt, sources=[], history=[],
                provider=data.get("provider", "gemini"),
                system_prompt="You are a fantasy shop inventory generator."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# =============================================================================
# PLAYER RECAP
# =============================================================================

@app.route("/api/recap/player", methods=["POST"])
def api_player_recap():
    """Generate player-facing recap."""
    from features import build_player_recap_prompt
    from generate import chat_with_context_stream

    data = request.json
    prompt = build_player_recap_prompt(data.get("notes", ""))

    def generate():
        try:
            stream = chat_with_context_stream(
                prompt, sources=[], history=[],
                provider=data.get("provider", "gemini"),
                system_prompt="You are writing a fun, spoiler-free session recap for players."
            )
            for chunk in stream:
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# =============================================================================
# RANDOM TABLES
# =============================================================================

@app.route("/api/tables/roll", methods=["POST"])
def api_roll_table():
    """Roll on a random table."""
    from features import roll_on_table
    data = request.json
    return jsonify(roll_on_table(data.get("table_path", "")))


# =============================================================================
# TIMER
# =============================================================================

@app.route("/api/timer/start", methods=["POST"])
def api_start_timer():
    """Start a countdown timer."""
    from features import start_timer
    data = request.json
    return jsonify(start_timer(data.get("name", "Timer"), data.get("rounds", 10)))


@app.route("/api/timer/stop", methods=["POST"])
def api_stop_timer():
    """Stop the timer."""
    from features import stop_timer
    return jsonify(stop_timer())


# =============================================================================
# QUICK NAME
# =============================================================================

@app.route("/api/name/quick")
def api_quick_name():
    """Get a quick random name."""
    from features import quick_name
    culture = request.args.get("culture", "")
    return jsonify(quick_name(culture))


if __name__ == "__main__":
    print("\n  Aetherion AI Web Interface")
    print("  http://localhost:5000\n")
    app.run(debug=True, port=5000, threaded=True)
