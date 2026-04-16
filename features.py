"""
Advanced features for Aetherion AI.

Features:
- Auto-linking: Convert entity names to [[wiki-links]]
- Character voice: AI responds as specific NPCs
- Relationship graph: Extract and visualize entity connections
- Session recap: Generate polished session summaries
- Consistency checker: Detect contradictions across notes
- Save to vault: Write AI responses as new notes
"""

import re
import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from config import VAULT_PATH, SYSTEM_PROMPT


# =============================================================================
# AUTO-LINKING
# =============================================================================

@lru_cache(maxsize=1)
def get_vault_entities() -> dict:
    """
    Extract all entity names from vault filenames.
    Returns dict mapping lowercase name -> actual filename.
    """
    entities = {}

    for md_file in VAULT_PATH.rglob("*.md"):
        # Skip hidden files and folders
        if any(part.startswith('.') for part in md_file.parts):
            continue

        name = md_file.stem  # Filename without .md
        entities[name.lower()] = name

    return entities


def clear_entity_cache():
    """Clear the entity cache (call after vault changes)."""
    get_vault_entities.cache_clear()


def auto_link_text(text: str) -> str:
    """
    Convert entity names in text to [[wiki-links]].

    Example:
        "Kael met the dragon" -> "[[Kael]] met the [[dragon]]"
    """
    entities = get_vault_entities()

    # Sort by length (longest first) to avoid partial matches
    sorted_names = sorted(entities.keys(), key=len, reverse=True)

    # Track what we've already linked to avoid double-linking
    linked_positions = []
    result = text

    for lower_name in sorted_names:
        actual_name = entities[lower_name]

        # Skip very short names (likely false positives)
        if len(lower_name) < 3:
            continue

        # Find all occurrences (case-insensitive, word boundaries)
        pattern = r'\b(' + re.escape(lower_name) + r')\b'

        for match in re.finditer(pattern, result, re.IGNORECASE):
            start, end = match.span()

            # Check if this position overlaps with existing link
            overlaps = any(
                start < link_end and end > link_start
                for link_start, link_end in linked_positions
            )

            # Check if already inside a [[link]]
            before = result[max(0, start-2):start]
            after = result[end:end+2]
            already_linked = '[[' in before or ']]' in after

            if not overlaps and not already_linked:
                # Replace with link (preserve original case in display)
                original_text = match.group(1)
                if original_text.lower() == actual_name.lower():
                    link = f'[[{actual_name}]]'
                else:
                    link = f'[[{actual_name}|{original_text}]]'

                # Calculate offset from replacement
                offset = len(link) - len(original_text)

                # Update result
                result = result[:start] + link + result[end:]

                # Update linked positions with offset
                linked_positions = [
                    (s + offset if s > start else s, e + offset if e > start else e)
                    for s, e in linked_positions
                ]
                linked_positions.append((start, start + len(link)))

    return result


# =============================================================================
# CHARACTER VOICE MODE
# =============================================================================

# Database locations
CHARACTER_PATH = VAULT_PATH / "Database" / "Characters"
RULER_PATH = VAULT_PATH / "Database" / "Rulers"


def get_characters() -> list[dict]:
    """
    Get list of characters from Database/Characters and Database/Rulers.
    Excludes database config files and deceased characters.
    Returns characters sorted by name with type indicator.
    """
    characters = []

    # Process both Characters and Rulers folders
    sources = [
        (CHARACTER_PATH, "characters_database.md", "Character"),
        (RULER_PATH, "rulers_database.md", "Ruler"),
    ]

    for base_path, db_file, char_type in sources:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            # Skip the database config file
            if md_file.name == db_file:
                continue

            # Skip hidden files
            if any(part.startswith('.') for part in md_file.parts):
                continue

            try:
                content = md_file.read_text(encoding='utf-8')

                # Check if deceased (for UI indication)
                is_deceased = 'Condition: Deceased' in content or 'Age: Deceased' in content

                # Extract kingdom from path
                relative = md_file.relative_to(base_path)
                kingdom = relative.parts[0] if len(relative.parts) > 1 else "Unknown"

                characters.append({
                    'name': md_file.stem,
                    'path': str(md_file.relative_to(VAULT_PATH)),
                    'kingdom': kingdom,
                    'type': char_type,
                    'deceased': is_deceased,
                    'preview': content[:300]
                })
            except Exception:
                continue

    return sorted(characters, key=lambda x: x['name'])


def _extract_personality_prompt(content: str) -> Optional[str]:
    """Extract PersonalityPrompt from YAML frontmatter."""
    if not content.startswith('---'):
        return None

    end_idx = content.find('---', 3)
    if end_idx == -1:
        return None

    frontmatter = content[3:end_idx]

    # Look for PersonalityPrompt field
    for line in frontmatter.split('\n'):
        if line.startswith('PersonalityPrompt:'):
            # Handle multi-line YAML string
            prompt_start = frontmatter.find('PersonalityPrompt:')
            prompt_text = frontmatter[prompt_start + 18:].strip()
            if prompt_text.startswith('|') or prompt_text.startswith('>'):
                # Multi-line block scalar
                lines = []
                for pline in frontmatter[prompt_start:].split('\n')[1:]:
                    if pline.startswith('  '):
                        lines.append(pline[2:])
                    elif pline.strip() and not pline.startswith(' '):
                        break
                return '\n'.join(lines)
            else:
                # Single line or quoted
                return prompt_text.strip('"\'')

    return None


def get_character_context(character_name: str) -> Optional[dict]:
    """
    Get character's note content and personality prompt.
    Searches Characters and Rulers folders.
    Returns dict with 'content' and 'personality_prompt' keys.
    """
    # Search in both character and ruler folders
    search_paths = [CHARACTER_PATH, RULER_PATH]

    for base_path in search_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if md_file.stem.lower() == character_name.lower():
                try:
                    content = md_file.read_text(encoding='utf-8')
                    personality_prompt = _extract_personality_prompt(content)

                    return {
                        'content': content,
                        'personality_prompt': personality_prompt
                    }
                except Exception:
                    return None

    # Fallback: search entire vault
    for md_file in VAULT_PATH.rglob("*.md"):
        if md_file.stem.lower() == character_name.lower():
            try:
                content = md_file.read_text(encoding='utf-8')
                return {
                    'content': content,
                    'personality_prompt': _extract_personality_prompt(content)
                }
            except Exception:
                return None

    return None


def build_character_prompt(character_name: str, character_data: dict) -> str:
    """
    Build a system prompt for speaking as a character.
    Uses the PersonalityPrompt from frontmatter if available.
    """
    content = character_data.get('content', '')
    personality_prompt = character_data.get('personality_prompt')

    if personality_prompt:
        # Use the custom personality prompt
        return f"""You are now roleplaying as {character_name}, a character from the world of Gryia.

PERSONALITY AND VOICE:
{personality_prompt}

CHARACTER INFORMATION:
{content}

INSTRUCTIONS:
- Embody the personality described above completely
- Only reference knowledge that {character_name} would reasonably have
- Stay in character throughout the conversation
- If asked about something the character wouldn't know, respond as the character would
- Use first person ("I", "my", "me")

Remember: You ARE {character_name}. Do not break character."""
    else:
        # Fallback to generic prompt
        return f"""You are now roleplaying as {character_name}, a character from the world of Gryia.

CHARACTER INFORMATION:
{content}

INSTRUCTIONS:
- Respond as {character_name} would, using their voice, mannerisms, and perspective
- Only reference knowledge that {character_name} would reasonably have
- Stay in character throughout the conversation
- If asked about something the character wouldn't know, respond as the character would (confusion, deflection, etc.)
- Use first person ("I", "my", "me")
- Match the character's speech patterns and personality

Remember: You ARE {character_name}. Do not break character."""


# =============================================================================
# RELATIONSHIP GRAPH
# =============================================================================

def extract_sections_from_file(file_path: Path) -> list[dict]:
    """
    Extract markdown sections (headers) from a file.
    Returns list of dicts with id, title, level, and links within that section.
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception:
        return []

    sections = []
    lines = content.split('\n')
    current_section = None
    current_content = []

    for line in lines:
        # Check for markdown header
        header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if header_match:
            # Save previous section
            if current_section:
                section_content = '\n'.join(current_content)
                current_section['links'] = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', section_content)
                sections.append(current_section)

            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            # Create URL-safe ID
            section_id = re.sub(r'[^a-zA-Z0-9\s-]', '', title).strip().replace(' ', '-').lower()

            current_section = {
                'id': section_id,
                'title': title,
                'level': level,
                'links': []
            }
            current_content = []
        else:
            current_content.append(line)

    # Don't forget the last section
    if current_section:
        section_content = '\n'.join(current_content)
        current_section['links'] = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', section_content)
        sections.append(current_section)

    return sections


def extract_links_from_file(file_path: Path) -> list[str]:
    """Extract all [[wiki-links]] from a file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        # Find all [[link]] or [[link|display]] patterns
        links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)
        return links
    except Exception:
        return []


def build_relationship_graph() -> dict:
    """
    Build a graph of relationships between notes.

    Returns:
        {
            "nodes": [{"id": "Name", "group": "folder", "file": "path"}],
            "links": [{"source": "Name1", "target": "Name2", "value": count}]
        }
    """
    nodes = {}
    links = {}

    for md_file in VAULT_PATH.rglob("*.md"):
        # Skip hidden files
        if any(part.startswith('.') for part in md_file.parts):
            continue

        source_name = md_file.stem
        relative_path = str(md_file.relative_to(VAULT_PATH))

        # Determine group from folder
        parts = relative_path.split(os.sep)
        group = parts[0] if len(parts) > 1 else "Root"

        # Add or update source node (update in case it was added as a reference first)
        if source_name not in nodes:
            nodes[source_name] = {
                "id": source_name,
                "group": group,
                "file": relative_path
            }
        elif nodes[source_name].get("file") is None:
            # Node exists but was added as a reference - update with actual file info
            nodes[source_name]["file"] = relative_path
            nodes[source_name]["group"] = group

        # Extract links
        linked_names = extract_links_from_file(md_file)

        for target_name in linked_names:
            # Create link key (sorted to avoid duplicates)
            link_key = tuple(sorted([source_name, target_name]))

            if link_key in links:
                links[link_key]["value"] += 1
            else:
                links[link_key] = {
                    "source": source_name,
                    "target": target_name,
                    "value": 1
                }

            # Add target node if not exists (might be external reference)
            if target_name not in nodes:
                nodes[target_name] = {
                    "id": target_name,
                    "group": "Reference",
                    "file": None
                }

    return {
        "nodes": list(nodes.values()),
        "links": list(links.values())
    }


# =============================================================================
# SESSION RECAP GENERATOR
# =============================================================================

SESSION_RECAP_PROMPT = """You are a D&D session scribe. Transform the rough session notes below into a polished,
narrative session recap suitable for a campaign journal.

FORMAT:
# Session [Number]: [Title]
*[Date if provided]*

## Summary
[2-3 sentence overview]

## Events
[Narrative account of what happened, written in past tense, third person]

## Notable Moments
- [Key decisions, funny moments, dramatic scenes]

## NPCs Encountered
- [[NPC Name]]: [Brief description of interaction]

## Locations Visited
- [[Location]]: [What happened there]

## Loot & Rewards
- [Items, gold, information gained]

## Hooks & Threads
- [Unresolved plot points, future leads]

---

ROUGH NOTES:
"""


def format_session_recap_prompt(raw_notes: str, session_number: Optional[int] = None) -> str:
    """Build the prompt for session recap generation."""
    prompt = SESSION_RECAP_PROMPT + raw_notes

    if session_number:
        prompt = prompt.replace("[Number]", str(session_number))

    return prompt


# =============================================================================
# CONSISTENCY CHECKER
# =============================================================================

def extract_entity_descriptions(entity_name: str) -> list[dict]:
    """
    Find all mentions of an entity and extract surrounding context.
    """
    mentions = []

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            # Find mentions with context
            pattern = r'.{0,100}' + re.escape(entity_name) + r'.{0,100}'
            matches = re.findall(pattern, content, re.IGNORECASE)

            for match in matches:
                mentions.append({
                    'file': str(md_file.relative_to(VAULT_PATH)),
                    'context': match.strip(),
                    'file_name': md_file.stem
                })
        except Exception:
            continue

    return mentions


CONSISTENCY_CHECK_PROMPT = """Analyze these excerpts about "{entity}" from different notes and identify any contradictions or inconsistencies.

EXCERPTS:
{excerpts}

Look for contradictions in:
- Physical descriptions (appearance, age, race)
- Relationships (family, allies, enemies)
- Locations (where they live, where they're from)
- Timeline (when events happened)
- Abilities or roles
- Personality traits

FORMAT YOUR RESPONSE AS:
## Consistency Analysis: {entity}

### Contradictions Found
[List any contradictions with file references]

### Ambiguities
[Things that could be clarified or unified]

### Consistent Elements
[Things that match across sources]

### Recommendations
[Suggested fixes or clarifications]

If no contradictions are found, state that the information is consistent.
"""


def build_consistency_prompt(entity_name: str, mentions: list[dict]) -> str:
    """Build prompt for consistency checking."""
    excerpts = "\n\n".join([
        f"**From {m['file']}:**\n> {m['context']}"
        for m in mentions[:20]  # Limit to avoid token overflow
    ])

    return CONSISTENCY_CHECK_PROMPT.format(
        entity=entity_name,
        excerpts=excerpts
    )


def get_major_entities(min_mentions: int = 3) -> list[dict]:
    """
    Get entities that appear in multiple files (good candidates for consistency check).
    """
    entity_counts = {}
    entities = get_vault_entities()

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8').lower()

            for lower_name, actual_name in entities.items():
                if len(lower_name) >= 3 and lower_name in content:
                    if actual_name not in entity_counts:
                        entity_counts[actual_name] = {'name': actual_name, 'count': 0, 'files': set()}
                    entity_counts[actual_name]['count'] += content.count(lower_name)
                    entity_counts[actual_name]['files'].add(md_file.stem)
        except Exception:
            continue

    # Filter and sort
    major = [
        {'name': e['name'], 'mentions': e['count'], 'files': len(e['files'])}
        for e in entity_counts.values()
        if len(e['files']) >= min_mentions
    ]

    return sorted(major, key=lambda x: x['files'], reverse=True)


# =============================================================================
# SAVE TO VAULT
# =============================================================================

def save_to_vault(
    content: str,
    filename: str,
    folder: str = "Notes",
    add_links: bool = True
) -> dict:
    """
    Save content as a new note in the vault.

    Args:
        content: The content to save
        filename: Name for the file (without .md)
        folder: Subfolder in vault (default: Notes)
        add_links: Whether to auto-link entities

    Returns:
        {"success": bool, "path": str, "message": str}
    """
    # Sanitize filename
    safe_filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    if not safe_filename:
        return {"success": False, "path": "", "message": "Invalid filename"}

    # Ensure folder exists
    target_folder = VAULT_PATH / folder
    target_folder.mkdir(parents=True, exist_ok=True)

    # Full path
    file_path = target_folder / f"{safe_filename}.md"

    # Check if file exists
    if file_path.exists():
        return {
            "success": False,
            "path": str(file_path.relative_to(VAULT_PATH)),
            "message": "File already exists"
        }

    # Process content
    final_content = content
    if add_links:
        final_content = auto_link_text(content)

    # Write file
    try:
        file_path.write_text(final_content, encoding='utf-8')

        # Clear entity cache since we added a new file
        clear_entity_cache()

        return {
            "success": True,
            "path": str(file_path.relative_to(VAULT_PATH)),
            "message": f"Saved to {folder}/{safe_filename}.md"
        }
    except Exception as e:
        return {
            "success": False,
            "path": "",
            "message": f"Error saving file: {str(e)}"
        }


def get_vault_folders() -> list[str]:
    """Get list of folders in the vault for folder selection."""
    folders = set()

    for item in VAULT_PATH.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            folders.add(item.name)

    return sorted(folders)


# =============================================================================
# CAMPAIGN MANAGEMENT
# =============================================================================

def get_campaign_overview() -> dict:
    """Get overview stats for campaign management dashboard."""
    from collections import defaultdict

    stats = {
        "characters": 0,
        "locations": 0,
        "factions": 0,
        "sessions": 0,
        "quests": 0,
        "items": 0,
        "total_notes": 0,
        "recent_files": [],
        "categories": defaultdict(int)
    }

    # Count files by category based on folder structure
    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        stats["total_notes"] += 1
        relative = md_file.relative_to(VAULT_PATH)

        # Categorize by folder
        if len(relative.parts) > 1:
            category = relative.parts[0].lower()
            stats["categories"][relative.parts[0]] += 1

            if "character" in category or "npc" in category:
                stats["characters"] += 1
            elif "location" in category or "place" in category or "point" in category:
                stats["locations"] += 1
            elif "faction" in category or "kingdom" in category or "organization" in category:
                stats["factions"] += 1
            elif "session" in category:
                stats["sessions"] += 1
            elif "quest" in category or "adventure" in category:
                stats["quests"] += 1
            elif "item" in category or "artifact" in category:
                stats["items"] += 1

    # Get recent files
    all_files = list(VAULT_PATH.rglob("*.md"))
    all_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    stats["recent_files"] = [
        {
            "name": f.stem,
            "path": str(f.relative_to(VAULT_PATH)),
            "modified": f.stat().st_mtime
        }
        for f in all_files[:10]
        if not any(part.startswith('.') for part in f.parts)
    ]

    return stats


# =============================================================================
# NPC QUICK CARDS
# =============================================================================

NPC_CARD_PROMPT = """Based on this character information, create a concise NPC quick reference card.

CHARACTER INFO:
{content}

FORMAT YOUR RESPONSE EXACTLY AS:
## {name}

**Appearance:** [1-2 sentences - what players see immediately]

**Voice/Mannerisms:** [How they speak, gestures, quirks]

**Motivation:** [What they want above all else]

**Secret:** [Something they're hiding]

**Useful For:** [How the party might interact with them - information, services, quests]

**Key Quote:** "[A characteristic line of dialogue]"

**Relationships:** [Key connections to other NPCs/factions]

Keep each section brief and table-ready. Focus on what's useful during play."""


def get_npc_for_card(name: str) -> Optional[dict]:
    """Get NPC content for generating a quick card."""
    for md_file in VAULT_PATH.rglob("*.md"):
        if md_file.stem.lower() == name.lower():
            try:
                content = md_file.read_text(encoding='utf-8')
                return {
                    "name": md_file.stem,
                    "path": str(md_file.relative_to(VAULT_PATH)),
                    "content": content
                }
            except Exception:
                pass
    return None


def build_npc_card_prompt(name: str, content: str) -> str:
    """Build prompt for NPC card generation."""
    return NPC_CARD_PROMPT.format(name=name, content=content[:4000])


# =============================================================================
# NAME GENERATOR
# =============================================================================

def analyze_naming_patterns() -> dict:
    """Analyze naming conventions from existing entities grouped by kingdom/culture."""
    from collections import defaultdict

    patterns = defaultdict(list)

    # Look in character and ruler folders
    search_paths = [
        VAULT_PATH / "Database" / "Characters",
        VAULT_PATH / "Database" / "Rulers",
        VAULT_PATH / "Database" / "Kingdoms",
    ]

    for base_path in search_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if md_file.name.endswith("_database.md"):
                continue

            # Get culture/kingdom from folder structure
            relative = md_file.relative_to(base_path)
            if len(relative.parts) > 1:
                culture = relative.parts[0]
            else:
                culture = "General"

            patterns[culture].append(md_file.stem)

    return dict(patterns)


NAME_GENERATOR_PROMPT = """Based on these existing names from {culture}, generate {count} new names that fit the same style and conventions.

EXISTING NAMES FROM {culture}:
{examples}

REQUIREMENTS:
- Match the phonetic patterns and style
- Names should feel like they belong to the same culture
- Provide both first names and full names where appropriate
- Include a mix of genders if the examples show variety

Generate {count} new names, one per line. Just the names, no explanations."""


def build_name_generator_prompt(culture: str, examples: list[str], count: int = 10) -> str:
    """Build prompt for name generation."""
    return NAME_GENERATOR_PROMPT.format(
        culture=culture,
        examples="\n".join(examples[:20]),
        count=count
    )


# =============================================================================
# TIMELINE
# =============================================================================

def extract_timeline_events() -> list[dict]:
    """Extract events with dates/years from vault notes."""
    events = []

    # Patterns for finding dates/years
    date_patterns = [
        r'(\d{1,4})\s*(?:AR|BR|AE|BE|Year)',  # Year with era marker
        r'(?:Year|year)\s*(\d{1,4})',  # Year X
        r'(\d{1,4})\s*years?\s*(?:ago|before|after)',  # X years ago
    ]

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            for pattern in date_patterns:
                for match in re.finditer(pattern, content, re.IGNORECASE):
                    # Get surrounding context
                    start = max(0, match.start() - 100)
                    end = min(len(content), match.end() + 100)
                    context = content[start:end].strip()

                    events.append({
                        "year": match.group(1),
                        "context": context,
                        "file": md_file.stem,
                        "path": str(md_file.relative_to(VAULT_PATH))
                    })
        except Exception:
            continue

    # Sort by year
    events.sort(key=lambda e: int(e["year"]) if e["year"].isdigit() else 0)

    return events


# =============================================================================
# FACTION RELATIONSHIPS
# =============================================================================

def extract_faction_relationships() -> dict:
    """Extract relationships between factions/kingdoms."""
    factions = {}
    relationships = []

    # Keywords that indicate relationships
    relationship_keywords = {
        "ally": "allied",
        "alliance": "allied",
        "allied": "allied",
        "enemy": "hostile",
        "enemies": "hostile",
        "war": "hostile",
        "conflict": "hostile",
        "hostile": "hostile",
        "rival": "rivalry",
        "rivalry": "rivalry",
        "trade": "trade",
        "trading": "trade",
        "vassal": "vassal",
        "tributary": "vassal",
        "neutral": "neutral",
    }

    # Find faction/kingdom files
    faction_paths = [
        VAULT_PATH / "Database" / "Kingdoms",
        VAULT_PATH / "Database" / "Factions",
        VAULT_PATH / "Database" / "Organizations",
    ]

    for base_path in faction_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if md_file.name.endswith("_database.md"):
                continue

            faction_name = md_file.stem
            factions[faction_name] = {
                "name": faction_name,
                "path": str(md_file.relative_to(VAULT_PATH)),
            }

            try:
                content = md_file.read_text(encoding='utf-8').lower()

                # Look for relationships with other factions
                for other_faction in factions:
                    if other_faction.lower() in content and other_faction != faction_name:
                        # Determine relationship type
                        rel_type = "mentioned"
                        for keyword, rel in relationship_keywords.items():
                            # Check if keyword appears near faction name
                            pattern = rf'{keyword}.{{0,50}}{re.escape(other_faction.lower())}|{re.escape(other_faction.lower())}.{{0,50}}{keyword}'
                            if re.search(pattern, content):
                                rel_type = rel
                                break

                        relationships.append({
                            "source": faction_name,
                            "target": other_faction,
                            "type": rel_type
                        })
            except Exception:
                continue

    return {
        "factions": list(factions.values()),
        "relationships": relationships
    }


# =============================================================================
# PROPHECY/MYSTERY TRACKER
# =============================================================================

def find_unresolved_threads() -> list[dict]:
    """Find prophecies, mysteries, and unresolved plot threads."""
    threads = []

    # Keywords that suggest unresolved elements
    mystery_keywords = [
        r'prophecy|prophecies|foretold|destined',
        r'mystery|mysterious|unknown|unexplained',
        r'secret|secrets|hidden|concealed',
        r'missing|disappeared|vanished|lost',
        r'unresolved|unanswered|unclear',
        r'rumor|rumors|legend|legends',
        r'foreshadow|hint|clue',
        r'\?\s*$',  # Questions at end of lines
    ]

    combined_pattern = '|'.join(f'({kw})' for kw in mystery_keywords)

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            for match in re.finditer(combined_pattern, content, re.IGNORECASE | re.MULTILINE):
                # Get the full line/sentence
                start = content.rfind('\n', 0, match.start()) + 1
                end = content.find('\n', match.end())
                if end == -1:
                    end = len(content)

                line = content[start:end].strip()
                if len(line) > 20:  # Skip very short matches
                    threads.append({
                        "type": "mystery" if "mystery" in match.group().lower() else
                               "prophecy" if "prophe" in match.group().lower() else
                               "secret" if "secret" in match.group().lower() else
                               "question" if "?" in match.group() else "thread",
                        "content": line[:200],
                        "file": md_file.stem,
                        "path": str(md_file.relative_to(VAULT_PATH))
                    })
        except Exception:
            continue

    return threads[:100]  # Limit results


# =============================================================================
# LORE GAP FINDER
# =============================================================================

def find_lore_gaps() -> list[dict]:
    """Identify missing information in worldbuilding."""
    gaps = []

    # Check for common missing fields in structured notes
    expected_fields = {
        "character": ["Age", "Race", "Occupation", "Location", "Relationships", "Background"],
        "location": ["Region", "Population", "Government", "Economy", "History"],
        "faction": ["Leader", "Goals", "Members", "Allies", "Enemies", "History"],
    }

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            relative_path = str(md_file.relative_to(VAULT_PATH)).lower()

            # Determine note type
            note_type = None
            if "character" in relative_path or "npc" in relative_path or "ruler" in relative_path:
                note_type = "character"
            elif "location" in relative_path or "place" in relative_path or "point" in relative_path:
                note_type = "location"
            elif "faction" in relative_path or "kingdom" in relative_path:
                note_type = "faction"

            if note_type and note_type in expected_fields:
                missing = []
                for field in expected_fields[note_type]:
                    if field.lower() not in content.lower():
                        missing.append(field)

                if missing:
                    gaps.append({
                        "file": md_file.stem,
                        "path": str(md_file.relative_to(VAULT_PATH)),
                        "type": note_type,
                        "missing_fields": missing
                    })

            # Check for placeholder text
            placeholder_patterns = [
                r'TODO',
                r'TBD',
                r'FIXME',
                r'\[.*?\?\]',
                r'unknown',
                r'needs work',
                r'expand later',
            ]

            for pattern in placeholder_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    gaps.append({
                        "file": md_file.stem,
                        "path": str(md_file.relative_to(VAULT_PATH)),
                        "type": "placeholder",
                        "missing_fields": [f"Contains '{pattern}' placeholder"]
                    })
                    break

        except Exception:
            continue

    return gaps


# Check for orphan references (links to non-existent files)
def find_broken_links() -> list[dict]:
    """Find wiki-links that point to non-existent files."""
    entities = get_vault_entities()
    broken = []

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)

            for link in links:
                if link.lower() not in entities:
                    broken.append({
                        "link": link,
                        "source_file": md_file.stem,
                        "source_path": str(md_file.relative_to(VAULT_PATH))
                    })
        except Exception:
            continue

    return broken


# =============================================================================
# DESCRIPTION EXPANDER
# =============================================================================

DESCRIPTION_EXPAND_PROMPT = """Expand these brief notes into vivid, immersive prose suitable for a fantasy RPG setting.

NOTES:
{notes}

CONTEXT (if relevant):
{context}

Write 2-3 paragraphs that:
- Paint a clear visual picture
- Include sensory details (sights, sounds, smells)
- Match the tone of epic fantasy
- Could be read aloud to players or used in worldbuilding documents

Do not add information that contradicts the notes. Expand and embellish, don't invent new facts."""


def build_description_prompt(notes: str, context: str = "") -> str:
    """Build prompt for description expansion."""
    return DESCRIPTION_EXPAND_PROMPT.format(notes=notes, context=context[:1000])


# =============================================================================
# SENSORY ENRICHMENT
# =============================================================================

SENSORY_PROMPT = """Add rich sensory details to this location or scene description.

CURRENT DESCRIPTION:
{description}

Add details for each sense:
- **Sight:** What catches the eye? Lighting, colors, movement?
- **Sound:** What ambient sounds? Voices, nature, machinery?
- **Smell:** What scents fill the air? Pleasant or unpleasant?
- **Touch/Feel:** Temperature? Humidity? Textures?
- **Atmosphere:** What's the emotional tone? Safe, dangerous, mysterious?

Integrate these naturally into 2-3 paragraphs of prose. Don't use bullet points in the final output."""


def build_sensory_prompt(description: str) -> str:
    """Build prompt for sensory enrichment."""
    return SENSORY_PROMPT.format(description=description[:2000])


# =============================================================================
# CAMPAIGN DATA PERSISTENCE (JSON in vault)
# =============================================================================

CAMPAIGN_DATA_FILE = VAULT_PATH / ".campaign-data.json"


def get_campaign_data() -> dict:
    """Load campaign state from vault JSON file."""
    default_data = {
        "current_date": None,
        "session_count": 0,
        "party": {},  # {name: {current_hp, max_hp, conditions, notes}}
        "quests": {},  # {name: {status, priority, notes}}
        "calendar": {
            "year": 1,
            "month": 1,
            "day": 1,
            "era": "AR"
        },
        "notes": "",
        # Initiative tracker
        "initiative": {
            "active": False,
            "round": 1,
            "turn": 0,
            "combatants": []  # [{name, initiative, hp, max_hp, conditions, is_pc, concentration}]
        },
        # Combat log
        "combat_log": [],  # [{timestamp, round, actor, action, target, damage, notes}]
        # Resources (spell slots, abilities)
        "resources": {},  # {pc_name: {spell_slots: {1: [used, max], ...}, abilities: {name: [used, max]}}}
        # Inspiration
        "inspiration": {},  # {pc_name: {has_inspiration: bool, earned_reason: str}}
        # Downtime
        "downtime": [],  # [{pc_name, activity, days, start_date, notes, completed}]
        # XP/Milestones
        "progression": {
            "mode": "milestone",  # or "xp"
            "party_xp": 0,
            "party_level": 1,
            "milestones": []  # [{name, date, description}]
        },
        # Rumors
        "rumors": [],  # [{text, source, true/false/unknown, revealed, session}]
        # Secrets
        "secrets": [],  # [{name, description, known_by, revealed, reveal_session}]
        # Handouts
        "handouts": [],  # [{title, content, given_session, given_to}]
        # Weather
        "current_weather": None,
        # Timer
        "timer": {
            "active": False,
            "name": "",
            "rounds_remaining": 0,
            "started_round": 0
        }
    }

    if not CAMPAIGN_DATA_FILE.exists():
        return default_data

    try:
        import json
        data = json.loads(CAMPAIGN_DATA_FILE.read_text(encoding='utf-8'))
        # Merge with defaults for any missing keys
        for key, value in default_data.items():
            if key not in data:
                data[key] = value
        return data
    except Exception:
        return default_data


def save_campaign_data(data: dict) -> dict:
    """Save campaign state to vault JSON file."""
    import json
    try:
        CAMPAIGN_DATA_FILE.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_campaign_data(updates: dict) -> dict:
    """Update specific fields in campaign data."""
    data = get_campaign_data()

    for key, value in updates.items():
        if key in data and isinstance(data[key], dict) and isinstance(value, dict):
            # Merge nested dicts
            data[key].update(value)
        else:
            data[key] = value

    return save_campaign_data(data)


def update_party_state(name: str, updates: dict) -> dict:
    """Update a party member's live state (HP, conditions, etc.)."""
    data = get_campaign_data()

    if name not in data["party"]:
        data["party"][name] = {
            "current_hp": None,
            "max_hp": None,
            "temp_hp": 0,
            "conditions": [],
            "notes": ""
        }

    data["party"][name].update(updates)
    return save_campaign_data(data)


def update_quest_state(name: str, updates: dict) -> dict:
    """Update a quest's status in campaign data."""
    data = get_campaign_data()

    if name not in data["quests"]:
        data["quests"][name] = {
            "status": "active",
            "priority": "normal",
            "notes": ""
        }

    data["quests"][name].update(updates)
    return save_campaign_data(data)


def advance_calendar(days: int = 1) -> dict:
    """Advance the in-world calendar by N days."""
    data = get_campaign_data()

    # Simple calendar - adjust for your world's calendar system
    data["calendar"]["day"] += days

    # Handle month rollover (assuming 30-day months)
    while data["calendar"]["day"] > 30:
        data["calendar"]["day"] -= 30
        data["calendar"]["month"] += 1

    # Handle year rollover (assuming 12 months)
    while data["calendar"]["month"] > 12:
        data["calendar"]["month"] -= 12
        data["calendar"]["year"] += 1

    save_campaign_data(data)
    return data["calendar"]


# =============================================================================
# INITIATIVE TRACKER
# =============================================================================

def start_combat() -> dict:
    """Initialize a new combat encounter."""
    data = get_campaign_data()
    data["initiative"] = {
        "active": True,
        "round": 1,
        "turn": 0,
        "combatants": []
    }
    data["combat_log"] = []
    save_campaign_data(data)
    return data["initiative"]


def end_combat() -> dict:
    """End current combat."""
    data = get_campaign_data()
    data["initiative"]["active"] = False
    save_campaign_data(data)
    return {"success": True}


def add_combatant(name: str, initiative: int, hp: int = 0, max_hp: int = 0,
                  is_pc: bool = False, group: str = "") -> dict:
    """Add a combatant to initiative order."""
    data = get_campaign_data()
    combatant = {
        "id": f"{name}_{len(data['initiative']['combatants'])}",
        "name": name,
        "initiative": initiative,
        "hp": hp,
        "max_hp": max_hp or hp,
        "temp_hp": 0,
        "conditions": [],
        "is_pc": is_pc,
        "concentration": None,
        "death_saves": {"successes": 0, "failures": 0},
        "group": group
    }
    data["initiative"]["combatants"].append(combatant)
    # Sort by initiative (descending)
    data["initiative"]["combatants"].sort(key=lambda c: c["initiative"], reverse=True)
    save_campaign_data(data)
    return combatant


def remove_combatant(combatant_id: str) -> dict:
    """Remove a combatant from initiative."""
    data = get_campaign_data()
    data["initiative"]["combatants"] = [
        c for c in data["initiative"]["combatants"] if c["id"] != combatant_id
    ]
    save_campaign_data(data)
    return {"success": True}


def update_combatant(combatant_id: str, updates: dict) -> dict:
    """Update a combatant's stats."""
    data = get_campaign_data()
    for c in data["initiative"]["combatants"]:
        if c["id"] == combatant_id:
            c.update(updates)
            break
    save_campaign_data(data)
    return {"success": True}


def next_turn() -> dict:
    """Advance to next turn in initiative."""
    data = get_campaign_data()
    init = data["initiative"]
    if not init["combatants"]:
        return init

    init["turn"] += 1
    if init["turn"] >= len(init["combatants"]):
        init["turn"] = 0
        init["round"] += 1
        # Decrement timer if active
        if data["timer"]["active"] and data["timer"]["rounds_remaining"] > 0:
            data["timer"]["rounds_remaining"] -= 1

    save_campaign_data(data)
    return init


def log_combat_action(actor: str, action: str, target: str = "",
                      damage: int = 0, notes: str = "") -> dict:
    """Log a combat action."""
    import time
    data = get_campaign_data()
    entry = {
        "timestamp": time.time(),
        "round": data["initiative"]["round"],
        "actor": actor,
        "action": action,
        "target": target,
        "damage": damage,
        "notes": notes
    }
    data["combat_log"].append(entry)
    save_campaign_data(data)
    return entry


# =============================================================================
# RESOURCE TRACKER
# =============================================================================

def get_pc_resources(pc_name: str) -> dict:
    """Get a PC's tracked resources."""
    data = get_campaign_data()
    return data["resources"].get(pc_name, {
        "spell_slots": {},
        "abilities": {},
        "items": {}
    })


def update_pc_resources(pc_name: str, resources: dict) -> dict:
    """Update a PC's resources."""
    data = get_campaign_data()
    if pc_name not in data["resources"]:
        data["resources"][pc_name] = {"spell_slots": {}, "abilities": {}, "items": {}}
    data["resources"][pc_name].update(resources)
    save_campaign_data(data)
    return {"success": True}


def use_spell_slot(pc_name: str, level: int) -> dict:
    """Use a spell slot."""
    data = get_campaign_data()
    if pc_name not in data["resources"]:
        data["resources"][pc_name] = {"spell_slots": {}, "abilities": {}, "items": {}}

    slots = data["resources"][pc_name]["spell_slots"]
    lvl_str = str(level)
    if lvl_str in slots and slots[lvl_str][0] < slots[lvl_str][1]:
        slots[lvl_str][0] += 1  # Increment used count
        save_campaign_data(data)
        return {"success": True, "remaining": slots[lvl_str][1] - slots[lvl_str][0]}
    return {"success": False, "error": "No slots available"}


def restore_spell_slots(pc_name: str, level: int = 0) -> dict:
    """Restore spell slots. If level=0, restore all."""
    data = get_campaign_data()
    if pc_name in data["resources"]:
        slots = data["resources"][pc_name]["spell_slots"]
        if level == 0:
            for lvl in slots:
                slots[lvl][0] = 0
        elif str(level) in slots:
            slots[str(level)][0] = 0
        save_campaign_data(data)
    return {"success": True}


def use_ability(pc_name: str, ability_name: str) -> dict:
    """Use a tracked ability."""
    data = get_campaign_data()
    if pc_name not in data["resources"]:
        return {"success": False, "error": "PC not found"}

    abilities = data["resources"][pc_name].get("abilities", {})
    if ability_name in abilities and abilities[ability_name][0] < abilities[ability_name][1]:
        abilities[ability_name][0] += 1
        save_campaign_data(data)
        return {"success": True, "remaining": abilities[ability_name][1] - abilities[ability_name][0]}
    return {"success": False, "error": "No uses available"}


def long_rest_resources(pc_name: str = "") -> dict:
    """Restore all resources for a PC or all PCs."""
    data = get_campaign_data()
    targets = [pc_name] if pc_name else list(data["resources"].keys())

    for name in targets:
        if name in data["resources"]:
            # Restore all spell slots
            for lvl in data["resources"][name].get("spell_slots", {}):
                data["resources"][name]["spell_slots"][lvl][0] = 0
            # Restore all abilities
            for ability in data["resources"][name].get("abilities", {}):
                data["resources"][name]["abilities"][ability][0] = 0

    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# INSPIRATION TRACKER
# =============================================================================

def toggle_inspiration(pc_name: str, reason: str = "") -> dict:
    """Toggle inspiration for a PC."""
    data = get_campaign_data()
    if pc_name not in data["inspiration"]:
        data["inspiration"][pc_name] = {"has_inspiration": False, "earned_reason": ""}

    current = data["inspiration"][pc_name]["has_inspiration"]
    data["inspiration"][pc_name] = {
        "has_inspiration": not current,
        "earned_reason": reason if not current else ""
    }
    save_campaign_data(data)
    return data["inspiration"][pc_name]


# =============================================================================
# DOWNTIME TRACKER
# =============================================================================

def add_downtime(pc_name: str, activity: str, days: int, notes: str = "") -> dict:
    """Add a downtime activity."""
    data = get_campaign_data()
    entry = {
        "id": f"dt_{len(data['downtime'])}_{pc_name}",
        "pc_name": pc_name,
        "activity": activity,
        "days": days,
        "start_date": f"Day {data['calendar']['day']}, Month {data['calendar']['month']}, Year {data['calendar']['year']}",
        "notes": notes,
        "completed": False
    }
    data["downtime"].append(entry)
    save_campaign_data(data)
    return entry


def complete_downtime(downtime_id: str) -> dict:
    """Mark a downtime activity as complete."""
    data = get_campaign_data()
    for dt in data["downtime"]:
        if dt["id"] == downtime_id:
            dt["completed"] = True
            break
    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# XP / MILESTONE TRACKER
# =============================================================================

def add_xp(amount: int, reason: str = "") -> dict:
    """Add XP to the party."""
    data = get_campaign_data()
    data["progression"]["party_xp"] += amount
    save_campaign_data(data)
    return {
        "party_xp": data["progression"]["party_xp"],
        "party_level": data["progression"]["party_level"]
    }


def set_party_level(level: int) -> dict:
    """Set the party level (for milestone tracking)."""
    data = get_campaign_data()
    data["progression"]["party_level"] = level
    save_campaign_data(data)
    return {"success": True}


def add_milestone(name: str, description: str = "") -> dict:
    """Add a milestone achievement."""
    data = get_campaign_data()
    milestone = {
        "name": name,
        "description": description,
        "date": f"Day {data['calendar']['day']}, Month {data['calendar']['month']}, Year {data['calendar']['year']}"
    }
    data["progression"]["milestones"].append(milestone)
    save_campaign_data(data)
    return milestone


# =============================================================================
# RUMOR BOARD
# =============================================================================

def add_rumor(text: str, source: str = "", status: str = "unknown") -> dict:
    """Add a rumor. Status: true, false, unknown."""
    data = get_campaign_data()
    rumor = {
        "id": f"rumor_{len(data['rumors'])}",
        "text": text,
        "source": source,
        "status": status,  # true, false, unknown
        "revealed": False,
        "session": data["session_count"]
    }
    data["rumors"].append(rumor)
    save_campaign_data(data)
    return rumor


def update_rumor(rumor_id: str, updates: dict) -> dict:
    """Update a rumor's status."""
    data = get_campaign_data()
    for rumor in data["rumors"]:
        if rumor["id"] == rumor_id:
            rumor.update(updates)
            break
    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# SECRETS TRACKER
# =============================================================================

def add_secret(name: str, description: str, known_by: list = None) -> dict:
    """Add a secret/revelation to track."""
    data = get_campaign_data()
    secret = {
        "id": f"secret_{len(data['secrets'])}",
        "name": name,
        "description": description,
        "known_by": known_by or [],
        "revealed": False,
        "reveal_session": None
    }
    data["secrets"].append(secret)
    save_campaign_data(data)
    return secret


def reveal_secret(secret_id: str, to_whom: list = None) -> dict:
    """Mark a secret as revealed."""
    data = get_campaign_data()
    for secret in data["secrets"]:
        if secret["id"] == secret_id:
            secret["revealed"] = True
            secret["reveal_session"] = data["session_count"]
            if to_whom:
                secret["known_by"].extend(to_whom)
            break
    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# HANDOUT LOG
# =============================================================================

def add_handout(title: str, content: str, given_to: list = None) -> dict:
    """Log a handout given to players."""
    data = get_campaign_data()
    handout = {
        "id": f"handout_{len(data['handouts'])}",
        "title": title,
        "content": content,
        "given_session": data["session_count"],
        "given_to": given_to or ["Party"]
    }
    data["handouts"].append(handout)
    save_campaign_data(data)
    return handout


# =============================================================================
# WEATHER GENERATOR
# =============================================================================

WEATHER_PROMPT = """Generate weather for a fantasy world.

SEASON: {season}
REGION TYPE: {region}
PREVIOUS WEATHER: {previous}

Generate realistic weather that:
- Fits the season and region
- Has some continuity with previous weather
- Includes temperature, precipitation, wind, and visibility
- Notes any special conditions (fog, storms, etc.)

Format as:
**Weather:** [Brief description]
**Temperature:** [Cold/Cool/Mild/Warm/Hot]
**Precipitation:** [None/Light/Moderate/Heavy]
**Wind:** [Calm/Light/Moderate/Strong/Gale]
**Visibility:** [Clear/Hazy/Foggy/Poor]
**Special:** [Any notable conditions]
**Mood:** [How this affects travel/combat/NPCs]"""


def build_weather_prompt(season: str, region: str, previous: str = "") -> str:
    """Build prompt for weather generation."""
    return WEATHER_PROMPT.format(season=season, region=region, previous=previous or "None")


def save_weather(weather: str) -> dict:
    """Save generated weather to campaign state."""
    data = get_campaign_data()
    data["current_weather"] = weather
    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# SHOP GENERATOR
# =============================================================================

SHOP_PROMPT = """Generate inventory for a fantasy shop.

SHOP TYPE: {shop_type}
SETTLEMENT SIZE: {settlement}
PARTY LEVEL: {level}
SPECIAL NOTES: {notes}

Generate a realistic shop inventory including:
- 5-10 common items (always in stock)
- 3-5 uncommon items (might be available)
- 0-2 rare items (special stock)
- Prices in gold pieces

Include brief descriptions and any quirks of the shopkeeper.

Format items as:
| Item | Description | Price |
|------|-------------|-------|"""


def build_shop_prompt(shop_type: str, settlement: str = "town",
                      level: int = 5, notes: str = "") -> str:
    """Build prompt for shop generation."""
    return SHOP_PROMPT.format(
        shop_type=shop_type,
        settlement=settlement,
        level=level,
        notes=notes or "None"
    )


# =============================================================================
# PLAYER-FACING RECAP
# =============================================================================

PLAYER_RECAP_PROMPT = """Create a player-friendly session recap that can be shared with the party.

SESSION NOTES:
{notes}

Create a recap that:
- Summarizes key events from the players' perspective
- Does NOT reveal DM secrets, hidden motivations, or future plot hooks
- Uses "you" to address the party
- Highlights player achievements and funny moments
- Reminds them of open questions they might investigate
- Is engaging and fun to read

Keep it to 2-3 paragraphs. No spoilers!"""


def build_player_recap_prompt(notes: str) -> str:
    """Build prompt for player-facing recap."""
    return PLAYER_RECAP_PROMPT.format(notes=notes[:4000])


# =============================================================================
# RANDOM TABLE ROLLER
# =============================================================================

def roll_on_table(table_path: str) -> dict:
    """Roll on a random table from the vault."""
    import random

    full_path = VAULT_PATH / table_path
    if not full_path.exists():
        return {"error": "Table not found"}

    try:
        content = full_path.read_text(encoding='utf-8')

        # Extract numbered entries (1. entry, 2. entry, etc.)
        entries = re.findall(r'^\s*(\d+)[\.\)]\s*(.+)$', content, re.MULTILINE)

        if not entries:
            # Try bullet points
            entries = re.findall(r'^\s*[-*]\s*(.+)$', content, re.MULTILINE)
            if entries:
                entries = [(str(i+1), e) for i, e in enumerate(entries)]

        if not entries:
            return {"error": "No table entries found"}

        # Roll
        roll = random.randint(1, len(entries))
        result = entries[roll - 1]

        return {
            "roll": roll,
            "total_entries": len(entries),
            "result": result[1] if isinstance(result, tuple) else result,
            "table": table_path
        }
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# TIMER / COUNTDOWN
# =============================================================================

def start_timer(name: str, rounds: int) -> dict:
    """Start a countdown timer."""
    data = get_campaign_data()
    data["timer"] = {
        "active": True,
        "name": name,
        "rounds_remaining": rounds,
        "started_round": data["initiative"]["round"]
    }
    save_campaign_data(data)
    return data["timer"]


def stop_timer() -> dict:
    """Stop the current timer."""
    data = get_campaign_data()
    data["timer"]["active"] = False
    save_campaign_data(data)
    return {"success": True}


# =============================================================================
# QUICK NAME GENERATOR (from vault patterns)
# =============================================================================

def quick_name(culture: str = "") -> dict:
    """Generate a quick random name based on vault patterns."""
    import random

    patterns = analyze_naming_patterns()

    if culture and culture in patterns:
        names = patterns[culture]
    elif patterns:
        # Pick a random culture
        culture = random.choice(list(patterns.keys()))
        names = patterns[culture]
    else:
        return {"error": "No naming patterns found"}

    if not names:
        return {"error": "No names found for culture"}

    # Simple approach: pick a random existing name as inspiration
    # More sophisticated would be to generate based on patterns
    base = random.choice(names)

    return {
        "name": base,
        "culture": culture,
        "note": "Picked from existing names. Use AI generator for new names."
    }


# =============================================================================
# CAMPAIGN SESSION MANAGEMENT
# =============================================================================

SESSIONS_PATH = VAULT_PATH / "Sessions"


def get_all_sessions() -> list[dict]:
    """Get all session notes from the vault."""
    sessions = []

    # Look in Sessions folder and any subfolder with "session" in name
    search_paths = [SESSIONS_PATH]
    for folder in VAULT_PATH.iterdir():
        if folder.is_dir() and "session" in folder.name.lower():
            search_paths.append(folder)

    for base_path in search_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if any(part.startswith('.') for part in md_file.parts):
                continue

            try:
                content = md_file.read_text(encoding='utf-8')

                # Try to extract session number from filename or content
                session_num = None
                num_match = re.search(r'session[_\s-]*(\d+)', md_file.stem, re.IGNORECASE)
                if num_match:
                    session_num = int(num_match.group(1))

                # Extract date if present
                date_match = re.search(r'\*?\*?(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\*?\*?', content)
                session_date = date_match.group(1) if date_match else None

                # Extract title (first H1 or H2)
                title_match = re.search(r'^#{1,2}\s+(.+)$', content, re.MULTILINE)
                title = title_match.group(1) if title_match else md_file.stem

                # Get preview (first paragraph after title)
                preview = ""
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if line.strip() and not line.startswith('#') and not line.startswith('*') and not line.startswith('-'):
                        preview = line.strip()[:200]
                        break

                sessions.append({
                    "number": session_num,
                    "title": title,
                    "date": session_date,
                    "preview": preview,
                    "file": md_file.stem,
                    "path": str(md_file.relative_to(VAULT_PATH)),
                    "modified": md_file.stat().st_mtime
                })
            except Exception:
                continue

    # Sort by session number, then by modified date
    sessions.sort(key=lambda s: (s["number"] or 0, s["modified"]), reverse=True)
    return sessions


def get_session_content(session_path: str) -> Optional[dict]:
    """Get full content of a specific session."""
    full_path = VAULT_PATH / session_path
    if not full_path.exists():
        return None

    try:
        content = full_path.read_text(encoding='utf-8')
        return {
            "path": session_path,
            "file": full_path.stem,
            "content": content
        }
    except Exception:
        return None


# =============================================================================
# "PREVIOUSLY ON..." GENERATOR
# =============================================================================

PREVIOUSLY_ON_PROMPT = """Based on these recent session notes, create a dramatic "Previously on..." recap that can be read aloud at the start of the next session.

RECENT SESSIONS:
{sessions}

Create a 2-3 paragraph dramatic recap that:
- Reads like a TV show recap narrator
- Highlights key events, decisions, and cliffhangers
- Reminds players of important NPCs and their motivations
- Ends with tension or anticipation for what's next
- Uses second person ("You discovered...", "Your party...", "You faced...")

Keep it under 300 words. Make it dramatic and engaging."""


def build_previously_on_prompt(sessions: list[dict]) -> str:
    """Build prompt for Previously On generator."""
    session_text = ""
    for session in sessions[:5]:  # Last 5 sessions max
        session_text += f"\n\n### {session.get('title', 'Session')}\n"
        session_text += session.get('content', session.get('preview', ''))[:2000]

    return PREVIOUSLY_ON_PROMPT.format(sessions=session_text)


# =============================================================================
# SESSION PREP ASSISTANT
# =============================================================================

SESSION_PREP_PROMPT = """Help me prepare for the next D&D session based on the current campaign state.

RECENT SESSIONS:
{recent_sessions}

ACTIVE QUESTS:
{quests}

RELEVANT NPCS:
{npcs}

PARTY STATUS:
{party}

Generate a session prep guide including:

## Recap Points
- Key events to remind players about
- Unresolved threads from last session

## Possible Directions
- 2-3 likely paths the party might take
- What they might encounter on each path

## NPCs to Prepare
- Which NPCs might appear
- Their current disposition toward the party
- Key dialogue or information they might share

## Encounters to Prepare
- Potential combat encounters
- Social encounters or negotiations
- Environmental challenges

## Hooks & Cliffhangers
- Ways to end the session dramatically
- New plot threads to introduce

## Notes & Reminders
- Anything time-sensitive
- Player backstory elements to incorporate"""


def build_session_prep_prompt(recent_sessions: str, quests: str, npcs: str, party: str) -> str:
    """Build prompt for session prep assistance."""
    return SESSION_PREP_PROMPT.format(
        recent_sessions=recent_sessions[:3000],
        quests=quests[:1500],
        npcs=npcs[:1500],
        party=party[:1000]
    )


# =============================================================================
# QUEST TRACKER
# =============================================================================

QUESTS_PATH = VAULT_PATH / "Quests"


def get_all_quests() -> list[dict]:
    """Extract quests from vault, determining status from content."""
    quests = []

    # Search multiple possible quest locations
    search_paths = [QUESTS_PATH]
    for folder in VAULT_PATH.iterdir():
        if folder.is_dir() and any(kw in folder.name.lower() for kw in ["quest", "mission", "objective", "adventure"]):
            search_paths.append(folder)

    for base_path in search_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if any(part.startswith('.') for part in md_file.parts):
                continue
            if md_file.name.endswith("_database.md"):
                continue

            try:
                content = md_file.read_text(encoding='utf-8')
                content_lower = content.lower()

                # Determine status from content
                status = "active"
                if any(kw in content_lower for kw in ["completed", "finished", "resolved", "done", "succeeded"]):
                    status = "completed"
                elif any(kw in content_lower for kw in ["failed", "abandoned", "impossible"]):
                    status = "failed"
                elif any(kw in content_lower for kw in ["on hold", "paused", "delayed", "pending"]):
                    status = "paused"

                # Extract priority if mentioned
                priority = "normal"
                if any(kw in content_lower for kw in ["urgent", "critical", "emergency", "time-sensitive"]):
                    priority = "high"
                elif any(kw in content_lower for kw in ["minor", "optional", "side"]):
                    priority = "low"

                # Extract quest giver if mentioned
                giver_match = re.search(r'(?:quest\s*giver|given\s*by|from|assigned\s*by)[:\s]*\[\[([^\]]+)\]\]', content, re.IGNORECASE)
                quest_giver = giver_match.group(1) if giver_match else None

                # Extract reward if mentioned
                reward_match = re.search(r'(?:reward|payment|compensation)[:\s]*([^\n]+)', content, re.IGNORECASE)
                reward = reward_match.group(1).strip()[:100] if reward_match else None

                # Get summary from first paragraph
                summary = ""
                lines = content.split('\n')
                for line in lines:
                    if line.strip() and not line.startswith('#') and not line.startswith('*') and len(line.strip()) > 30:
                        summary = line.strip()[:200]
                        break

                quests.append({
                    "name": md_file.stem,
                    "path": str(md_file.relative_to(VAULT_PATH)),
                    "status": status,
                    "priority": priority,
                    "quest_giver": quest_giver,
                    "reward": reward,
                    "summary": summary,
                    "modified": md_file.stat().st_mtime
                })
            except Exception:
                continue

    # Sort: active first, then by priority, then by modified
    priority_order = {"high": 0, "normal": 1, "low": 2}
    status_order = {"active": 0, "paused": 1, "completed": 2, "failed": 3}
    quests.sort(key=lambda q: (status_order.get(q["status"], 1), priority_order.get(q["priority"], 1), -q["modified"]))

    return quests


def create_quest_note(quest_data: dict) -> dict:
    """Create a new quest note in the vault."""
    name = quest_data.get("name", "New Quest")
    status = quest_data.get("status", "active")
    quest_giver = quest_data.get("quest_giver", "")
    reward = quest_data.get("reward", "")
    description = quest_data.get("description", "")
    objectives = quest_data.get("objectives", [])

    content = f"""# {name}

**Status:** {status}
**Quest Giver:** {"[[" + quest_giver + "]]" if quest_giver else "Unknown"}
**Reward:** {reward if reward else "TBD"}

## Description
{description}

## Objectives
"""
    for obj in objectives:
        content += f"- [ ] {obj}\n"

    content += """
## Notes

## Progress Log
"""

    return save_to_vault(content, name, folder="Quests", add_links=False)


# =============================================================================
# PARTY ROSTER
# =============================================================================

PARTY_PATH = VAULT_PATH / "Party"


def get_party_members() -> list[dict]:
    """Get party member information from vault."""
    members = []

    # Search in Party folder and also look for PC markers
    search_paths = [PARTY_PATH]
    for folder in VAULT_PATH.iterdir():
        if folder.is_dir() and any(kw in folder.name.lower() for kw in ["party", "player", "pc"]):
            search_paths.append(folder)

    for base_path in search_paths:
        if not base_path.exists():
            continue

        for md_file in base_path.rglob("*.md"):
            if any(part.startswith('.') for part in md_file.parts):
                continue
            if md_file.name.endswith("_database.md"):
                continue

            try:
                content = md_file.read_text(encoding='utf-8')

                # Extract class
                class_match = re.search(r'(?:class|classes)[:\s]*([^\n|]+)', content, re.IGNORECASE)
                char_class = class_match.group(1).strip()[:50] if class_match else None

                # Extract race
                race_match = re.search(r'(?:race|species)[:\s]*([^\n|]+)', content, re.IGNORECASE)
                race = race_match.group(1).strip()[:30] if race_match else None

                # Extract level
                level_match = re.search(r'(?:level)[:\s]*(\d+)', content, re.IGNORECASE)
                level = int(level_match.group(1)) if level_match else None

                # Extract player name if mentioned
                player_match = re.search(r'(?:player|played\s*by)[:\s]*([^\n|]+)', content, re.IGNORECASE)
                player = player_match.group(1).strip()[:30] if player_match else None

                # Extract HP if mentioned
                hp_match = re.search(r'(?:HP|hit\s*points|health)[:\s]*(\d+)(?:\s*/\s*(\d+))?', content, re.IGNORECASE)
                if hp_match:
                    current_hp = int(hp_match.group(1))
                    max_hp = int(hp_match.group(2)) if hp_match.group(2) else current_hp
                else:
                    current_hp = max_hp = None

                # Extract AC if mentioned
                ac_match = re.search(r'(?:AC|armor\s*class)[:\s]*(\d+)', content, re.IGNORECASE)
                ac = int(ac_match.group(1)) if ac_match else None

                members.append({
                    "name": md_file.stem,
                    "path": str(md_file.relative_to(VAULT_PATH)),
                    "class": char_class,
                    "race": race,
                    "level": level,
                    "player": player,
                    "current_hp": current_hp,
                    "max_hp": max_hp,
                    "ac": ac
                })
            except Exception:
                continue

    # Sort by level descending, then name
    members.sort(key=lambda m: (-(m["level"] or 0), m["name"]))
    return members


def update_party_member(name: str, updates: dict) -> dict:
    """Update party member stats (HP, conditions, etc.)."""
    for md_file in VAULT_PATH.rglob("*.md"):
        if md_file.stem.lower() == name.lower():
            try:
                content = md_file.read_text(encoding='utf-8')

                # Update HP if provided
                if "current_hp" in updates and "max_hp" in updates:
                    hp_pattern = r'(?:HP|hit\s*points|health)[:\s]*\d+(?:\s*/\s*\d+)?'
                    new_hp = f"HP: {updates['current_hp']}/{updates['max_hp']}"
                    if re.search(hp_pattern, content, re.IGNORECASE):
                        content = re.sub(hp_pattern, new_hp, content, flags=re.IGNORECASE)
                    else:
                        # Add HP line after first header
                        content = re.sub(r'(^#[^\n]+\n)', rf'\1\n**{new_hp}**\n', content, count=1)

                # Update conditions if provided
                if "conditions" in updates:
                    conditions_text = ", ".join(updates["conditions"]) if updates["conditions"] else "None"
                    cond_pattern = r'(?:conditions?|status)[:\s]*[^\n]+'
                    new_cond = f"Conditions: {conditions_text}"
                    if re.search(cond_pattern, content, re.IGNORECASE):
                        content = re.sub(cond_pattern, new_cond, content, flags=re.IGNORECASE)

                md_file.write_text(content, encoding='utf-8')
                return {"success": True, "message": f"Updated {name}"}
            except Exception as e:
                return {"success": False, "message": str(e)}

    return {"success": False, "message": f"Character '{name}' not found"}


# =============================================================================
# NPC ENCOUNTER LOG
# =============================================================================

def get_npc_encounters() -> list[dict]:
    """Track NPCs the party has encountered, with relationship status."""
    encounters = []
    entities = get_vault_entities()

    # Look for NPCs mentioned in session notes
    session_files = []
    for md_file in VAULT_PATH.rglob("*.md"):
        path_lower = str(md_file).lower()
        if "session" in path_lower:
            session_files.append(md_file)

    # Track which NPCs appear in sessions
    npc_sessions = {}
    for session_file in session_files:
        try:
            content = session_file.read_text(encoding='utf-8')
            links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)

            for link in links:
                if link not in npc_sessions:
                    npc_sessions[link] = []
                npc_sessions[link].append(session_file.stem)
        except Exception:
            continue

    # Get NPC details
    for npc_name, sessions in npc_sessions.items():
        # Check if it's likely an NPC (exists in Characters or has character-like path)
        npc_file = None
        for md_file in VAULT_PATH.rglob("*.md"):
            if md_file.stem.lower() == npc_name.lower():
                path_str = str(md_file).lower()
                if any(kw in path_str for kw in ["character", "npc", "ruler", "people"]):
                    npc_file = md_file
                    break

        if npc_file:
            try:
                content = npc_file.read_text(encoding='utf-8')

                # Try to determine disposition
                disposition = "neutral"
                content_lower = content.lower()
                if any(kw in content_lower for kw in ["ally", "friend", "helpful", "trusted"]):
                    disposition = "friendly"
                elif any(kw in content_lower for kw in ["enemy", "hostile", "antagonist", "villain"]):
                    disposition = "hostile"

                # Check if alive
                is_alive = "deceased" not in content_lower and "dead" not in content_lower

                encounters.append({
                    "name": npc_name,
                    "path": str(npc_file.relative_to(VAULT_PATH)),
                    "sessions_appeared": sessions,
                    "appearance_count": len(sessions),
                    "disposition": disposition,
                    "is_alive": is_alive,
                    "last_session": sessions[-1] if sessions else None
                })
            except Exception:
                continue

    # Sort by appearance count
    encounters.sort(key=lambda e: e["appearance_count"], reverse=True)
    return encounters[:50]  # Top 50 most encountered


# =============================================================================
# IN-WORLD CALENDAR
# =============================================================================

def get_calendar_events() -> list[dict]:
    """Extract in-world dates and events from the vault."""
    events = []

    # Common fantasy calendar patterns
    month_patterns = [
        r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([A-Z][a-z]+)',  # 15th of Flamerule
        r'([A-Z][a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?',  # Flamerule 15
        r'(\d{1,2})/(\d{1,2})/(\d{1,4})',  # 15/6/1492
        r'Day\s+(\d+)',  # Day 42
    ]

    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')

            for pattern in month_patterns:
                for match in re.finditer(pattern, content):
                    # Get context
                    start = max(0, match.start() - 50)
                    end = min(len(content), match.end() + 150)
                    context = content[start:end].strip()

                    events.append({
                        "date_text": match.group(0),
                        "context": context,
                        "file": md_file.stem,
                        "path": str(md_file.relative_to(VAULT_PATH))
                    })
        except Exception:
            continue

    return events[:100]


def get_campaign_calendar_state() -> dict:
    """Get the current in-world date if tracked."""
    # Look for a calendar/date tracking file
    calendar_files = ["Calendar.md", "Current Date.md", "Timeline.md", "Campaign Date.md"]

    for filename in calendar_files:
        for md_file in VAULT_PATH.rglob(filename):
            try:
                content = md_file.read_text(encoding='utf-8')

                # Look for "current date" markers
                current_match = re.search(r'(?:current\s*date|today|present)[:\s]*([^\n]+)', content, re.IGNORECASE)
                if current_match:
                    return {
                        "current_date": current_match.group(1).strip(),
                        "source_file": str(md_file.relative_to(VAULT_PATH))
                    }
            except Exception:
                continue

    return {"current_date": None, "source_file": None}


# =============================================================================
# ENCOUNTER BUILDER
# =============================================================================

ENCOUNTER_PROMPT = """Create a D&D encounter based on these parameters:

PARTY:
{party}

SETTING:
{setting}

DIFFICULTY: {difficulty}
TYPE: {encounter_type}

Design an encounter including:

## Encounter: [Name]

### Setup
- Location description
- How the encounter begins
- Environmental features

### Enemies/NPCs
- List each creature/NPC with brief tactics
- Include any relevant stats or abilities to remember

### Tactics
- How enemies will fight/behave
- Special abilities they'll use
- Retreat conditions

### Complications
- Optional twists or escalations
- Environmental hazards
- Reinforcements

### Resolution
- What happens if party wins
- What happens if party loses/flees
- Loot/rewards

### Notes for DM
- Key things to remember
- Voices/personalities to portray"""


def build_encounter_prompt(party: str, setting: str, difficulty: str, encounter_type: str) -> str:
    """Build prompt for encounter generation."""
    return ENCOUNTER_PROMPT.format(
        party=party[:1000],
        setting=setting[:500],
        difficulty=difficulty,
        encounter_type=encounter_type
    )


# =============================================================================
# LOOT GENERATOR
# =============================================================================

LOOT_PROMPT = """Generate a D&D loot drop appropriate for this context:

PARTY LEVEL: {level}
ENCOUNTER TYPE: {encounter_type}
SETTING: {setting}

Generate loot including:
- Gold/coins (appropriate amount for level)
- 1-3 mundane items (contextually appropriate)
- 0-2 interesting items (not magical, but useful or valuable)
- 0-1 magical item (if appropriate for difficulty)

For each item, provide:
- Name
- Brief description
- Approximate value in gold
- Any mechanical effects

Make items feel grounded in the setting. Include details that make them memorable."""


def build_loot_prompt(level: int, encounter_type: str, setting: str) -> str:
    """Build prompt for loot generation."""
    return LOOT_PROMPT.format(
        level=level,
        encounter_type=encounter_type,
        setting=setting[:500]
    )


# =============================================================================
# RANDOM TABLES
# =============================================================================

def get_random_tables() -> list[dict]:
    """Find random tables in the vault for quick rolling."""
    tables = []

    # Look for files with "table", "random", "roll" in name or containing d20/d100
    for md_file in VAULT_PATH.rglob("*.md"):
        if any(part.startswith('.') for part in md_file.parts):
            continue

        try:
            content = md_file.read_text(encoding='utf-8')
            name_lower = md_file.stem.lower()

            # Check if it's a random table
            is_table = (
                any(kw in name_lower for kw in ["table", "random", "roll", "generator"]) or
                re.search(r'\bd\d+\b', content) or  # Contains dice notation
                re.search(r'^\d+\.\s', content, re.MULTILINE)  # Numbered list
            )

            if is_table:
                # Try to extract table entries
                entries = re.findall(r'^\s*\d+[\.\)]\s*(.+)$', content, re.MULTILINE)

                tables.append({
                    "name": md_file.stem,
                    "path": str(md_file.relative_to(VAULT_PATH)),
                    "entry_count": len(entries),
                    "preview": entries[:5] if entries else []
                })
        except Exception:
            continue

    return tables


# =============================================================================
# SESSION NOTES TEMPLATE
# =============================================================================

def create_session_note(session_number: int, title: str = "", date: str = "") -> dict:
    """Create a new session note from template."""
    if not title:
        title = f"Session {session_number}"

    content = f"""# Session {session_number}: {title}
*{date if date else "Date: TBD"}*

## Previously...
> [Quick recap of last session]

## Session Goals
- [ ] Primary objective
- [ ] Secondary objective

## Events

### Scene 1: [Title]


### Scene 2: [Title]


## NPCs Encountered
- [[NPC Name]]:

## Locations
- [[Location]]:

## Loot & Rewards
-

## Notes & Quotes
>

## Hooks for Next Session
-

## XP/Milestones
-

---
*Session ended: *
"""

    filename = f"Session {session_number:03d}"
    if title and title != f"Session {session_number}":
        filename += f" - {title}"

    return save_to_vault(content, filename, folder="Sessions", add_links=False)
