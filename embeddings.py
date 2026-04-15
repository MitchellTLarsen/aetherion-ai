"""Embedding generation and storage using OpenAI/Gemini and ChromaDB."""
import hashlib
import time
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings
from google import genai
from openai import OpenAI
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from config import (
    OPENAI_API_KEY,
    GEMINI_API_KEY,
    VAULT_PATH,
    CHROMA_PATH,
    EMBEDDING_PROVIDER,
    OPENAI_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_MODEL,
    INCLUDE_FOLDERS,
    EXCLUDED_FILES,
)

console = Console()

# Rate limiting for Gemini (100 requests per minute = ~1.67 per second)
GEMINI_REQUESTS_PER_MINUTE = 100
GEMINI_MIN_DELAY = 60.0 / GEMINI_REQUESTS_PER_MINUTE  # ~0.6 seconds

_last_gemini_request = 0.0

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


def get_chroma_client() -> chromadb.PersistentClient:
    """Get ChromaDB persistent client."""
    return chromadb.PersistentClient(
        path=str(CHROMA_PATH),
        settings=Settings(anonymized_telemetry=False)
    )


def get_collection(client: chromadb.PersistentClient) -> chromadb.Collection:
    """Get or create the Aetherion collection."""
    # Use different collection names for different embedding providers
    collection_name = f"aetherion_{EMBEDDING_PROVIDER}"
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )


def should_index_file(file_path: Path) -> bool:
    """Check if a file should be indexed."""
    # Skip non-markdown files
    if file_path.suffix.lower() != ".md":
        return False

    # Skip hidden folders (starting with .)
    for part in file_path.parts:
        if part.startswith("."):
            return False

    # Only include files in INCLUDE_FOLDERS
    in_included_folder = False
    for part in file_path.parts:
        if part in INCLUDE_FOLDERS:
            in_included_folder = True
            break

    if not in_included_folder:
        return False

    # Skip excluded files
    if file_path.name in EXCLUDED_FILES:
        return False

    # Skip excalidraw files
    if ".excalidraw" in file_path.name:
        return False

    return True


def get_file_hash(content: str) -> str:
    """Generate hash of file content for change detection."""
    return hashlib.md5(content.encode()).hexdigest()


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[dict]:
    """Split text into overlapping chunks with metadata."""
    chunks = []

    # Split by headers first for better semantic chunks
    lines = text.split("\n")
    current_chunk = []
    current_header = ""
    current_size = 0

    for line in lines:
        # Detect headers
        if line.startswith("#"):
            # Save current chunk if it has content
            if current_chunk and current_size > 100:
                chunks.append({
                    "text": "\n".join(current_chunk),
                    "header": current_header
                })
            current_chunk = [line]
            current_header = line.strip("# ").strip()
            current_size = len(line)
        else:
            current_chunk.append(line)
            current_size += len(line)

            # If chunk is getting too large, split it
            if current_size > chunk_size:
                chunks.append({
                    "text": "\n".join(current_chunk),
                    "header": current_header
                })
                # Keep overlap
                overlap_lines = []
                overlap_size = 0
                for l in reversed(current_chunk):
                    if overlap_size + len(l) > overlap:
                        break
                    overlap_lines.insert(0, l)
                    overlap_size += len(l)
                current_chunk = overlap_lines
                current_size = overlap_size

    # Don't forget the last chunk
    if current_chunk and current_size > 50:
        chunks.append({
            "text": "\n".join(current_chunk),
            "header": current_header
        })

    return chunks


def create_embedding_openai(client: OpenAI, text: str) -> list[float]:
    """Create embedding using OpenAI."""
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding


def create_embedding_gemini(text: str, max_retries: int = 3) -> list[float]:
    """Create embedding using Gemini (free!) with rate limiting."""
    global _last_gemini_request

    # Rate limiting
    elapsed = time.time() - _last_gemini_request
    if elapsed < GEMINI_MIN_DELAY:
        time.sleep(GEMINI_MIN_DELAY - elapsed)

    client = get_gemini_client()

    for attempt in range(max_retries):
        try:
            _last_gemini_request = time.time()
            result = client.models.embed_content(
                model=GEMINI_EMBEDDING_MODEL,
                contents=text,
            )
            return result.embeddings[0].values
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                # Rate limited, wait and retry
                wait_time = (attempt + 1) * 30  # 30s, 60s, 90s
                console.print(f"[yellow]Rate limited, waiting {wait_time}s...[/yellow]")
                time.sleep(wait_time)
            else:
                raise

    raise Exception("Max retries exceeded for Gemini embedding")


def create_embedding(text: str, openai_client: Optional[OpenAI] = None) -> list[float]:
    """Create embedding using configured provider."""
    if EMBEDDING_PROVIDER == "openai":
        if openai_client is None:
            openai_client = get_openai_client()
        return create_embedding_openai(openai_client, text)
    else:
        return create_embedding_gemini(text)


def index_vault(force: bool = False) -> dict:
    """Index all markdown files in the vault."""
    openai_client = get_openai_client() if EMBEDDING_PROVIDER == "openai" else None
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)

    console.print(f"[dim]Using {EMBEDDING_PROVIDER} embeddings[/dim]")
    if EMBEDDING_PROVIDER == "gemini":
        console.print(f"[dim]Rate limited to {GEMINI_REQUESTS_PER_MINUTE} req/min (free tier)[/dim]")

    # Get existing documents
    existing = {}
    if not force:
        try:
            results = collection.get(include=["metadatas"])
            for id_, meta in zip(results["ids"], results["metadatas"]):
                if meta and "file_hash" in meta:
                    existing[meta.get("file_path", "")] = meta["file_hash"]
        except Exception:
            pass

    # Find all markdown files
    md_files = [f for f in VAULT_PATH.rglob("*.md") if should_index_file(f)]

    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "errors": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Indexing vault...", total=len(md_files))

        for file_path in md_files:
            try:
                content = file_path.read_text(encoding="utf-8")
                file_hash = get_file_hash(content)
                rel_path = str(file_path.relative_to(VAULT_PATH))

                # Skip if unchanged
                if not force and rel_path in existing and existing[rel_path] == file_hash:
                    stats["skipped"] += 1
                    progress.advance(task)
                    continue

                # Remove old entries for this file
                try:
                    old_ids = collection.get(
                        where={"file_path": rel_path},
                        include=[]
                    )["ids"]
                    if old_ids:
                        collection.delete(ids=old_ids)
                except Exception:
                    pass

                # Chunk the content
                chunks = chunk_text(content)
                if not chunks:
                    progress.advance(task)
                    continue

                # Create embeddings and store
                ids = []
                embeddings = []
                documents = []
                metadatas = []

                for i, chunk in enumerate(chunks):
                    chunk_id = f"{rel_path}#{i}"
                    embedding = create_embedding(chunk["text"], openai_client)

                    ids.append(chunk_id)
                    embeddings.append(embedding)
                    documents.append(chunk["text"])
                    metadatas.append({
                        "file_path": rel_path,
                        "file_hash": file_hash,
                        "chunk_index": i,
                        "header": chunk["header"],
                        "file_name": file_path.stem
                    })

                collection.add(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )

                stats["indexed"] += 1
                stats["chunks"] += len(chunks)
                progress.update(task, description=f"Indexed: {rel_path[:40]}...")

            except Exception as e:
                console.print(f"[red]Error indexing {file_path.name}: {e}[/red]")
                stats["errors"] += 1

            progress.advance(task)

    return stats


def get_stats() -> dict:
    """Get statistics about the indexed vault."""
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)

    count = collection.count()

    # Get unique files
    results = collection.get(include=["metadatas"])
    files = set()
    for meta in results["metadatas"]:
        if meta and "file_path" in meta:
            files.add(meta["file_path"])

    return {
        "total_chunks": count,
        "total_files": len(files),
        "db_path": str(CHROMA_PATH),
        "provider": EMBEDDING_PROVIDER
    }
