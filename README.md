# Aetherion AI

A RAG-powered CLI for semantic search and AI-assisted world-building over your Obsidian vault. Built for the Aetherion D&D campaign setting.

## What is RAG?

**RAG (Retrieval Augmented Generation)** means the AI doesn't just make things up - it searches your vault first, finds relevant lore, and generates responses grounded in your existing content. This keeps your world consistent.

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│ Your Query  │ ──▶ │ Search Vault │ ──▶ │ Add Context │ ──▶ │ AI Response  │
│             │     │ (Retrieval)  │     │ to Prompt   │     │ (Generation) │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘
```

Without RAG: "Tell me about Athamos" → AI invents random facts
With RAG: "Tell me about Athamos" → AI reads your notes first, then responds accurately

## Features

### Core RAG
- **Hybrid Search** - Semantic embeddings + keyword matching + cross-encoder reranking
- **RAG Chat** - AI chat that pulls relevant context from your vault
- **Streaming Responses** - See text as it generates
- **Multi-Query Retrieval** - Breaks complex questions into sub-queries
- **Context Compression** - Summarizes context to fit more information
- **Chat History** - Save and load conversation sessions
- **Obsidian Links** - Clickable links to open sources in Obsidian
- **Multiple Providers** - OpenAI, Gemini, Claude, Ollama, Groq, OpenRouter

### Web Interface
- **Character Voice Mode** - AI responds as your NPCs with their personality
- **Auto-Linking** - Convert entity names to [[wiki-links]]
- **Save to Vault** - Write AI responses as new notes
- **Relationship Graph** - Interactive D3.js visualization of vault connections
- **Worldbuilding Hub** - Writing tools for fantasy worldbuilding
- **Campaign Manager** - Full D&D campaign management with persistent state

### Campaign Manager Features
- **Initiative Tracker** - Combat turn order with HP, conditions, death saves
- **Party Roster** - Live HP tracking, conditions, inspiration
- **Quest Tracker** - Track quests with status and rewards
- **Session Management** - Create sessions, generate recaps
- **Resource Tracker** - Spell slots, abilities, long rest
- **Rumor Board** - Track rumors with true/false/unknown status
- **Secrets Tracker** - Track story secrets and revelations
- **In-World Calendar** - Track campaign date, advance time
- **Generators** - Encounters, loot, weather, shops, names
- **Random Tables** - Roll on any table in your vault

## Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/aetherion-ai.git
cd aetherion-ai

# Create and activate a virtual environment
# macOS / Linux
python -m venv venv
source venv/bin/activate

# Windows PowerShell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install -r requirements.txt
```

### Windows note

If `python` points to an MSYS2/Git Bash Python on Windows, some packages may fail to install cleanly.
Prefer the official Windows Python launcher:

```powershell
py -3.12 -m venv venv
py -3.12 -m pip --python .\venv\Scripts\python.exe install -r requirements.txt
```

Create a `.env` file:

```bash
cp .env.example .env  # If .env.example exists
```

If this repository does not include `.env.example`, create `.env` manually in the project root.

Edit `.env` with your settings:

```
# Required: Path to your Obsidian vault
VAULT_PATH=~/Documents/YourVault
OBSIDIAN_VAULT_NAME=YourVault

# API Keys (at least one required)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...  # optional, has free tier
```

## Quick Start

```bash
# Index your vault (first time)
python cli.py index

# Start web interface (recommended)
python cli.py web

# Or use terminal chat
python cli.py chat
```

## Web Interface

Launch a browser-based chat UI similar to Gemini AI Studio:

```bash
python cli.py web
python cli.py web --port 8080  # Custom port
```

**Chat Features:**
- Dark/light theme (LegendKeeper-inspired styling)
- Streaming responses with markdown rendering
- Source panel showing context used
- Token count and cost estimates
- Character voice mode (speak as NPCs)
- Auto-linking entities to wiki-links
- Save AI responses directly to vault
- Chat history saved locally

**Additional Tools (accessible from sidebar):**
- **Worldbuilding Hub** (`/worldbuilding`) - Writing tools dashboard
- **Campaign Manager** (`/campaign`) - Full D&D campaign management
- **Relationship Graph** (`/graph`) - Interactive D3.js visualization of vault connections

### Worldbuilding Hub

A dedicated dashboard for fantasy writing and worldbuilding:

| Tool | Description |
|------|-------------|
| **NPC Cards** | Generate quick-reference cards for NPCs |
| **Name Generator** | Generate names matching your world's cultures |
| **Timeline** | View dated events extracted from your notes |
| **Factions** | Visualize faction relationships |
| **Plot Threads** | Find unresolved mysteries and prophecies |
| **Lore Gaps** | Identify missing information and broken links |
| **Description Expander** | Expand brief notes into vivid prose |
| **Sensory Enrichment** | Add sensory details to location descriptions |

### Campaign Manager

A comprehensive D&D campaign management tool with persistent state:

**Session Management:**
- Session log with templated note creation
- "Previously On..." dramatic recap generator
- Player-friendly recap generator (spoiler-free)
- Session prep assistant

**Party & Combat:**
- Party roster with live HP tracking
- Condition tracking (Poisoned, Stunned, etc.)
- Initiative tracker with turn order
- Combat log
- Round-based countdown timers
- Death saves tracking
- Resource tracker (spell slots, abilities)
- Inspiration tracker

**Quest & Progression:**
- Quest tracker with status management
- XP tracking
- Milestone tracking
- Party level management

**Information Tracking:**
- Rumor board (true/false/unknown status)
- Secrets tracker (hidden/revealed)
- Handout log
- Downtime activity tracker
- NPC encounter history

**Generators:**
- Encounter builder (by difficulty/type)
- Loot generator (by level/context)
- Weather generator (by season/region)
- Shop inventory generator
- Quick name generator
- Random table roller

**Calendar:**
- In-world date tracking
- Advance by day/week/month
- View dated events from notes

All campaign data persists to `.campaign-data.json` in your vault and syncs across machines.

### Relationship Graph

Interactive visualization of connections between notes:

- Force-directed D3.js graph
- Filter to show only files (not references)
- Drill into files to see section-level connections
- Connection depth controls (+1, +2, +3 relationships)
- Color-coded by folder/category
- Click to view file content
- Optimized for large vaults

## Commands

### Index Your Vault

```bash
python cli.py index          # incremental update
python cli.py index --force  # full re-index
```

### Search

```bash
python cli.py search "the Stormborn covenant"
python cli.py search "taverns" -n 20           # more results
python cli.py search "magic" -c                # compact output
python cli.py search "characters" --no-rerank  # skip reranking
```

### Chat (Interactive)

```bash
python cli.py chat                    # default settings
python cli.py chat --no-confirm       # skip confirmation
python cli.py chat --no-stream        # disable streaming
python cli.py chat --load my-session  # resume saved session
```

**In-chat commands:**
| Command | Description |
|---------|-------------|
| `/sources` | Toggle source display |
| `/confirm` | Toggle confirm-before-send |
| `/stream` | Toggle streaming |
| `/cost` | Show pricing for current provider |
| `/deep` | Toggle deep search (multi-query + compression) |
| `/open <path>` | View a block |
| `/save <name>` | Save session |
| `/load <name>` | Load session |
| `/list` | List saved sessions |
| `/clear` | Clear history |
| `/prompt` | Set custom system prompt |

**Cost Estimation:**

Before each message is sent, you'll see token count and estimated cost:
```
Found 8 relevant chunks:
  1. Database/Religions/Stormborn.md (92%)
  ...
Estimated: ~$0.0023 (1,847 in + ~500 out)
Send to LLM? [y/n/more/open/skip]:
```

Free providers (Ollama, Gemini free tier) show:
```
Estimated: FREE (1,523 tokens)
```

### Watch for Changes

```bash
python cli.py watch  # auto-reindex on file changes
```

### Other Commands

```bash
python cli.py ask "What is the history of Athamos?"
python cli.py block "Database/Locations/City.md#history"
python cli.py related "Notes/Session5.md"
python cli.py connections "Database/Locations/City.md"  # Smart Connections style
python cli.py stats
python cli.py sessions   # list saved chat sessions
python cli.py providers  # list available AI providers

# D&D helpers
python cli.py encounter "The Sunken Grotto" --level 5 --difficulty hard
python cli.py npc "Athamos Harbor" --role "smuggler"
python cli.py expand "Database/Locations/Tavern.md" --aspect "history"
```

### Smart Connections

View semantically related notes for any file (similar to the Obsidian plugin):

```bash
python cli.py connections "Database/NPCs/Captain.md"
python cli.py connections "Database/NPCs/Captain.md" -n 20  # More results
```

Output shows relevance bars and clickable links:
```
████████████████████ 100%
   The Stormborn Covenant
   Database/Religions/Stormborn.md

██████████████░░░░░░ 72%
   Athamos Harbor
   Database/Locations/Athamos.md
```

### World-Building Tools

These commands help you develop your world consistently:

```bash
# Find gaps and suggest additions (NO PROMPT NEEDED)
python cli.py gaps                    # Analyzes entire vault for missing content
python cli.py gaps --folder Database  # Check specific folder

# Check new content for consistency
python cli.py check "The Stormborn worship fire gods"

# Find all references to an entity
python cli.py refs "Athamos"

# Validate timeline consistency
python cli.py timeline

# Expand a stub note with AI-generated lore
python cli.py lore "Database/Locations/NewTown.md"
python cli.py lore "Database/Locations/NewTown.md" --save  # Write to file

# Flesh out a note using its template structure
python cli.py flesh "Database/Kingdoms/MyKingdom.md"        # Preview
python cli.py flesh "Database/Kingdoms/MyKingdom.md" --save # Save with backup
python cli.py flesh "Database/NPCs/Someone.md" --no-check   # Skip consistency check
```

#### The `gaps` Command (Zero-Prompt Suggestions)

Analyzes your vault and suggests what's missing:

```bash
python cli.py gaps
```

**What it does:**
1. Scans all notes, identifies stubs (< 100 words)
2. Compares against typical world-building categories
3. AI analyzes for missing elements (economy, magic system, calendar, etc.)
4. Suggests specific notes to create

**Example output:**
```
Stub notes (12 files < 100 words):
  Raezgard     23 words   Database/Kingdoms/Raezgard.md
  Dark Elves   45 words   Database/Races/Dark Elves.md
  ...

Gap Analysis:
- Missing: No magic system documentation
- Missing: No calendar or time-keeping system
- Underdeveloped: Raezgard has no culture section
- Suggested: Create "Database/Systems/Economy.md"
```

#### The `flesh` Command (Smart Expansion)

Expands notes based on templates while maintaining world consistency:

```bash
python cli.py flesh "Database/Kingdoms/SomeKingdom.md" --save
```

**What it does:**
1. Reads the note and identifies its type (Kingdom, NPC, Location, etc.)
2. Loads the matching template from `Templates/`
3. Finds empty sections that need content
4. Gathers context from 4 sources:
   - Related notes (semantic search)
   - Timeline (temporal consistency)
   - Cross-references (how this entity is mentioned elsewhere)
   - Linked entities (from frontmatter relationships)
5. Generates content for empty sections
6. Runs consistency check against existing lore
7. Saves with backup (.md.bak)

#### The `check` Command (Consistency Validation)

Before adding new lore, check if it contradicts existing content:

```bash
python cli.py check "The Athamian Republic was founded by dwarves"
```

**What it checks:**
- Direct contradictions with established facts
- Tone and naming convention consistency
- Connections to existing elements
- Suggestions for better fit

## Module System

Features can be toggled on/off in the web interface settings:

| Module | Features |
|--------|----------|
| **Worldbuilding Tools** | Worldbuilding Hub, Relationship Graph, NPC Cards, Name Generator, Timeline, Factions, Plot Threads, Lore Gaps, Writing Tools |
| **Campaign Manager** | Campaign Manager, Session Recap, Consistency Checker, Initiative, Quests, Party, Calendar, Generators |
| **Character Voice** | Character voice mode (speak as NPCs) |

Settings persist to localStorage.

## Configuration

Edit `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `EMBEDDING_PROVIDER` | `openai` | `openai` or `gemini` |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-large` | Embedding model |
| `GPT_MODEL` | `gpt-5-nano` | Chat model |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini chat model |
| `USE_RERANKER` | `True` | Enable cross-encoder reranking |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `DEFAULT_PROVIDER` | `gpt` | Default chat provider (`gpt` or `gemini`) |
| `INCLUDE_FOLDERS` | `Database, Notes, Other Notes, Story` | Folders to index |
| `OBSIDIAN_VAULT_NAME` | `Aetherion` | For clickable `obsidian://` links |

## Methodology

### The Full RAG Pipeline

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           INDEXING (once)                                  │
├────────────────────────────────────────────────────────────────────────────┤
│  Markdown Files ──▶ Chunk by Headers ──▶ Generate Embeddings ──▶ ChromaDB │
│                     (1000 chars max)     (3072-dim vectors)    (persistent)│
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                           RETRIEVAL (each query)                           │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Query ──┬──▶ Embed Query ──▶ Cosine Similarity ──▶ Top N semantic matches │
│          │                                                    │            │
│          │                                                    ▼            │
│          └──▶ Extract Keywords ──▶ Exact Matching ──▶ Top N keyword matches│
│                                                               │            │
│                                                               ▼            │
│                                              Reciprocal Rank Fusion (RRF)  │
│                                                               │            │
│                                                               ▼            │
│                                              Cross-Encoder Reranking       │
│                                                               │            │
│                                                               ▼            │
│                                                    Final Ranked Results    │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                           GENERATION                                       │
├────────────────────────────────────────────────────────────────────────────┤
│  System Prompt + Retrieved Context + Chat History + User Query ──▶ LLM    │
│                                                                    │       │
│                                                                    ▼       │
│                                                          Streamed Response │
└────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Breakdown

#### 1. Indexing (`python cli.py index`)

- Scans vault for `.md` files in configured folders (Database, Notes, Other Notes, Story)
- Splits each file into chunks at headers (max ~1000 characters)
- Converts each chunk to a 3072-dimensional embedding vector using OpenAI
- Stores vectors + metadata in ChromaDB (local database)
- Tracks file hashes for incremental updates (only re-indexes changed files)

#### 2. Semantic Search

- Your query gets converted to the same 3072-dim vector
- ChromaDB finds chunks with similar vectors (cosine similarity)
- Chunks "about" similar topics score high, even without exact word matches
- Example: "ocean worship" finds "Covenant of the Stormborn" (semantically related)

#### 3. Keyword Search

- Extracts important words from your query (filters out "the", "is", etc.)
- Finds chunks containing those exact words
- Scores by frequency (more mentions = higher score)
- Catches proper nouns and specific terms semantic search might miss

#### 4. Reciprocal Rank Fusion (RRF)

- Combines semantic and keyword results
- Documents appearing in both lists get boosted
- Formula: `score = 1/(k + rank)` summed across lists
- Balances "aboutness" (semantic) with "exactness" (keyword)

#### 5. Cross-Encoder Reranking

- Takes top candidates and re-scores them
- Unlike embeddings (query and doc encoded separately), cross-encoder sees them together
- More accurate but slower - that's why it only reranks top results
- Final scores normalized: best = 100%, worst = 0%

#### 6. Generation

- Retrieved chunks become "context" in the prompt
- LLM sees: system prompt + your lore + conversation history + your question
- Response is grounded in your actual content, not hallucinated

### Deep Search Mode (`/deep`)

For complex questions needing broader context:

1. **Multi-Query** - LLM generates 3 related search queries from your question
2. **Parallel Search** - Searches with all queries, deduplicates results
3. **Compression** - Summarizes lower-ranked sources to fit more context

### Scoring (What the % Means)

The percentage shown for each source is **relative relevance**:
- 100% = best match found
- 50% = half as relevant as the best
- Lower % = less relevant but still matched

It's not "confidence" - it's ranking. A 70% result from a small vault might be weaker than a 40% result from a large, specific vault.

## File Structure

```
aetherion-ai/
├── cli.py              # CLI commands
├── web.py              # Flask web server & API endpoints
├── config.py           # Configuration
├── embeddings.py       # Indexing & embedding generation
├── search.py           # Hybrid search + reranking
├── generate.py         # LLM generation, streaming, history
├── features.py         # Advanced features (character voice, campaign management, etc.)
├── providers.py        # AI provider integrations
├── costs.py            # Token counting & cost estimation
├── templates/
│   ├── index.html      # Main chat interface
│   ├── graph.html      # Relationship graph visualization
│   ├── worldbuilding.html  # Worldbuilding hub
│   └── campaign.html   # Campaign manager
├── static/
│   ├── style.css       # Main stylesheet
│   └── app.js          # Frontend JavaScript
├── chroma_db/          # Vector database
├── chat_history/       # Saved sessions
├── .env                # API keys
└── requirements.txt
```

## Data Storage

Campaign data is stored in your Obsidian vault for portability:

| File | Location | Purpose |
|------|----------|---------|
| `.campaign-data.json` | Vault root | Campaign state (party HP, quests, initiative, rumors, secrets, etc.) |
| `Sessions/*.md` | Vault | Session notes |
| `Quests/*.md` | Vault | Quest notes |
| `Party/*.md` | Vault | Player character notes |

This data syncs with your vault (via Obsidian Sync, iCloud, Dropbox, Git, etc.).

## AI Providers

Multiple AI providers are supported. Use `-p` flag to switch:

```bash
python cli.py chat -p anthropic    # Use Claude
python cli.py chat -p ollama       # Use local Ollama
python cli.py ask "question" -p groq  # Use Groq (fast!)
```

List configured providers:
```bash
python cli.py providers
```

| Provider | Models | Notes |
|----------|--------|-------|
| **openai** / **gpt** | gpt-5-nano, gpt-4o, gpt-4o-mini | Default, requires API key |
| **gemini** | gemini-2.5-flash-lite, gemini-2.0-flash | Generous free tier |
| **anthropic** / **claude** | claude-sonnet-4-20250514, claude-3-opus | High quality |
| **ollama** | llama3, mistral, codellama | Local, free, private |
| **groq** | llama-3.3-70b-versatile, mixtral-8x7b | Very fast, free tier |
| **openrouter** | Any model via OpenRouter | Access to 100+ models |

### Setup Providers

Add API keys to `.env`:

```bash
# Required (at least one)
OPENAI_API_KEY=sk-...

# Optional providers
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...

# Ollama (no key needed, just run Ollama locally)
OLLAMA_BASE_URL=http://localhost:11434
```

Install optional dependencies:
```bash
pip install anthropic  # For Claude
pip install groq       # For Groq
pip install ollama     # For Ollama
```

## Models Used

| Component | Model | Purpose |
|-----------|-------|---------|
| **Embeddings** | `text-embedding-3-large` (OpenAI) | Converts text to 3072-dim vectors for semantic search |
| **Chat/Generation** | Configurable per provider | Generates responses, expands content |
| **Reranking** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Runs locally, re-scores search results for accuracy |

## Tips

- Use `/deep` for complex questions that need broader context
- Save good conversations with `/save` for reference
- Run `watch` in a separate terminal to keep index fresh
- Use `--no-confirm` for faster chat flow once you trust the search
- Toggle `/stream` off if you prefer seeing complete responses
- Use `gaps` periodically to find underdeveloped areas
- Use `flesh --save` to quickly expand stub notes with consistent lore
- Use `check` before adding major new lore to catch contradictions

## Glossary

| Term | Meaning |
|------|---------|
| **RAG** | Retrieval Augmented Generation - search first, then generate |
| **Embedding** | A vector (list of numbers) representing text meaning |
| **Semantic Search** | Finding similar meaning, not just matching words |
| **Cross-Encoder** | Model that scores query+document together (more accurate) |
| **RRF** | Reciprocal Rank Fusion - combining multiple ranked lists |
| **Chunk** | A section of a note (split at headers) |
| **ChromaDB** | Local vector database storing your embeddings |
