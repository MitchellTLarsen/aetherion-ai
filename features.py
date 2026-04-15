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

        # Add source node
        if source_name not in nodes:
            nodes[source_name] = {
                "id": source_name,
                "group": group,
                "file": relative_path
            }

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
