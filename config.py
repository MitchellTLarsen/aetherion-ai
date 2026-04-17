"""Configuration management for Scribe AI assistant."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent / ".env")

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")

# Ollama (local)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Set HF token for sentence-transformers
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN

# Paths
# VAULT_PATH must be set in .env file - there is no default
_vault_path = os.getenv("VAULT_PATH")
if not _vault_path:
    raise ValueError("VAULT_PATH environment variable must be set in .env file")
VAULT_PATH = Path(_vault_path).expanduser()

if not VAULT_PATH.exists():
    raise ValueError(f"VAULT_PATH does not exist: {VAULT_PATH}")

CHROMA_PATH = Path(__file__).parent / "chroma_db"
CHROMA_PATH.mkdir(exist_ok=True)
CHAT_HISTORY_PATH = Path(__file__).parent / "chat_history"
CHAT_HISTORY_PATH.mkdir(exist_ok=True)

# Obsidian vault name (for obsidian:// links)
OBSIDIAN_VAULT_NAME = os.getenv("OBSIDIAN_VAULT_NAME", "MyVault")

# Embedding settings
# Options: "openai" or "gemini"
EMBEDDING_PROVIDER = "openai"  # Default to OpenAI (requires API credits)

# OpenAI embedding
OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"
OPENAI_EMBEDDING_DIMENSIONS = 3072

# Gemini embedding (free!)
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
GEMINI_EMBEDDING_DIMENSIONS = 768

# Reranker model (cross-encoder for better ranking)
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
USE_RERANKER = True

# Lore folders to index (only these folders will be indexed)
INCLUDE_FOLDERS = {"Database", "Notes", "Other Notes", "Story"}

# Excluded files within included folders
EXCLUDED_FILES = {"Untitled", "Buttons.md", "To Do List.md", "Prompts.md", "Image Gen.md"}

# Supported file extensions for indexing
SUPPORTED_EXTENSIONS = {
    ".md",       # Markdown
    ".txt",      # Plain text
    ".rst",      # reStructuredText
    ".org",      # Org Mode
    ".html",     # HTML (tags stripped)
    ".htm",      # HTML variant
    ".pdf",      # PDF (requires pypdf)
    ".docx",     # Word documents (requires python-docx)
    ".rtf",      # Rich Text Format
    ".tex",      # LaTeX (commands stripped)
    ".json",     # JSON (pretty printed)
    ".csv",      # CSV files
}

# Generation settings - Models for each provider
GPT_MODEL = "gpt-5.4-nano"                    # OpenAI - latest & cheap ($0.20/1M in)
GEMINI_MODEL = "gemini-2.5-flash-lite"        # Google - generous free tier
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"  # Anthropic - balanced model
OLLAMA_MODEL = "llama3"                       # Local - depends on what you have installed
GROQ_MODEL = "llama-3.3-70b-versatile"        # Groq - fast and free tier available
OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"  # OpenRouter - access to many models

# Available GPT models for UI selection
GPT_MODELS = {
    # GPT-5.4 (Latest)
    "gpt-5.4-nano": "GPT-5.4 Nano ($0.20/1M)",
    "gpt-5.4-mini": "GPT-5.4 Mini ($0.75/1M)",
    "gpt-5.4": "GPT-5.4 ($2.50/1M)",
    "gpt-5.4-pro": "GPT-5.4 Pro ($30/1M)",
    # GPT-5.2
    "gpt-5.2": "GPT-5.2 ($1.75/1M)",
    "gpt-5.2-pro": "GPT-5.2 Pro ($21/1M)",
    # GPT-5.0
    "gpt-5-nano": "GPT-5 Nano ($0.05/1M)",
    "gpt-5-mini": "GPT-5 Mini ($0.25/1M)",
    "gpt-5": "GPT-5 ($1.25/1M)",
}

# Default generation provider
# Options: "openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"
DEFAULT_PROVIDER = "gpt"

# =============================================================================
# SYSTEM PROMPTS - Module-based
# =============================================================================

# Base system prompt (generic AI writing assistant)
SYSTEM_PROMPT = """You are Scribe, an intelligent AI writing assistant with access to a knowledge vault.

Your role is to:
1. Help research, organize, and expand upon the content in the user's vault
2. Answer questions using relevant context from indexed documents
3. Generate new content that maintains consistency with existing materials
4. Assist with writing, editing, and brainstorming

Always maintain consistency with established information provided in the context.
Write in a style that matches the existing content.
When generating new content, consider how it connects to existing elements.
"""

# Module-specific system prompt extensions
MODULE_PROMPTS = {
    "fantasy": """

Additionally, you specialize in fantasy worldbuilding and TTRPG (D&D, Pathfinder, etc.) support:
- Help develop worlds, characters, factions, religions, and lore consistently
- Assist with session planning, encounter design, and NPC creation
- Generate content that fits fantasy settings (evocative, immersive, detailed)
- Track campaign elements like initiative, resources, and session notes
""",
    "academic": """

Additionally, you specialize in academic and research writing:
- Help organize research notes and literature reviews
- Assist with citations and reference management
- Support structured academic writing (papers, theses, dissertations)
- Help identify gaps in research and suggest connections
""",
    "fiction": """

Additionally, you specialize in fiction writing:
- Help develop characters, plots, and story arcs
- Assist with world-building for any genre
- Support outlining and structural planning
- Help maintain consistency in narrative elements
""",
    "technical": """

Additionally, you specialize in technical documentation:
- Write clear, precise documentation with proper structure
- Include code examples, diagrams descriptions, and step-by-step instructions
- Use consistent terminology and formatting
- Focus on accuracy, completeness, and usability
""",
    "journaling": """

Additionally, you are a reflective journaling companion:
- Help with personal reflection and self-discovery
- Ask thoughtful questions to deepen understanding
- Maintain a warm, supportive, non-judgmental tone
- Help organize thoughts and identify patterns over time
""",
}

def get_system_prompt(modules: list = None, custom_prompt: str = None) -> str:
    """Get system prompt with active module extensions."""
    prompt = SYSTEM_PROMPT
    if modules:
        for module in modules:
            if module in MODULE_PROMPTS:
                prompt += MODULE_PROMPTS[module]
    # Append custom prompt if provided
    if custom_prompt and custom_prompt.strip():
        prompt += "\n" + custom_prompt.strip()
    return prompt

