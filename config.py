"""Configuration management for Aetherion AI assistant."""
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
OBSIDIAN_VAULT_NAME = os.getenv("OBSIDIAN_VAULT_NAME", "Aetherion")

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

# Generation settings - Models for each provider
GPT_MODEL = "gpt-5-nano"                      # OpenAI - cheapest option
GEMINI_MODEL = "gemini-2.5-flash-lite"        # Google - generous free tier
ANTHROPIC_MODEL = "claude-sonnet-4-20250514"  # Anthropic - balanced model
OLLAMA_MODEL = "llama3"                       # Local - depends on what you have installed
GROQ_MODEL = "llama-3.3-70b-versatile"        # Groq - fast and free tier available
OPENROUTER_MODEL = "anthropic/claude-3.5-sonnet"  # OpenRouter - access to many models

# Default generation provider
# Options: "openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"
DEFAULT_PROVIDER = "gpt"

# Custom system prompt (can be overridden per session)
SYSTEM_PROMPT = """You are Aetherion, an AI assistant for a fantasy world-building project and D&D campaign setting.

You have deep knowledge of the world of Gryia, including:
- The Athamian Republic (maritime nation with the Covenant of the Stormborn religion)
- The Azorian Empire
- The Confederation of Raezgard
- Various settlements, characters, religions, and lore

Your role is to:
1. Help expand and develop the world consistently
2. Assist with D&D session planning and encounter design
3. Generate new content that fits the established tone and lore
4. Answer questions about the world's history, politics, and cultures

Always maintain consistency with established lore provided in the context.
Write in a style that matches the existing content - evocative, detailed, and immersive.
When generating new content, consider how it connects to existing elements.
"""

