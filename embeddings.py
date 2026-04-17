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
    SUPPORTED_EXTENSIONS,
)
import re
import json
import csv
import io

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
    """Get or create the Scribe AI collection."""
    # Use different collection names for different embedding providers
    collection_name = f"aetherion_{EMBEDDING_PROVIDER}"
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )


def should_index_file(file_path: Path) -> bool:
    """Check if a file should be indexed."""
    # Check if extension is supported
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
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


def extract_text(file_path: Path) -> str:
    """Extract text content from various file types."""
    ext = file_path.suffix.lower()

    try:
        # Plain text formats - read directly
        if ext in {".md", ".txt", ".rst", ".org"}:
            return file_path.read_text(encoding="utf-8")

        # HTML - strip tags
        elif ext in {".html", ".htm"}:
            content = file_path.read_text(encoding="utf-8")
            return strip_html_tags(content)

        # PDF - extract text
        elif ext == ".pdf":
            return extract_pdf_text(file_path)

        # Word documents
        elif ext == ".docx":
            return extract_docx_text(file_path)

        # RTF - strip formatting
        elif ext == ".rtf":
            return extract_rtf_text(file_path)

        # LaTeX - strip commands
        elif ext == ".tex":
            content = file_path.read_text(encoding="utf-8")
            return strip_latex_commands(content)

        # JSON - pretty print
        elif ext == ".json":
            content = file_path.read_text(encoding="utf-8")
            data = json.loads(content)
            return json.dumps(data, indent=2)

        # CSV - convert to readable text
        elif ext == ".csv":
            return extract_csv_text(file_path)

        else:
            # Fallback: try to read as text
            return file_path.read_text(encoding="utf-8")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not extract text from {file_path.name}: {e}[/yellow]")
        return ""


def strip_html_tags(html: str) -> str:
    """Remove HTML tags and extract text."""
    # Remove script and style elements
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    html = re.sub(r'<[^>]+>', ' ', html)
    # Clean up whitespace
    html = re.sub(r'\s+', ' ', html)
    # Decode HTML entities
    html = html.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return html.strip()


def extract_pdf_text(file_path: Path) -> str:
    """Extract text from PDF files."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(file_path))
        text_parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        return "\n\n".join(text_parts)
    except ImportError:
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(str(file_path))
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)
        except ImportError:
            console.print("[yellow]PDF support requires: pip install pypdf[/yellow]")
            return ""
    except Exception as e:
        console.print(f"[yellow]PDF extraction failed: {e}[/yellow]")
        return ""


def extract_docx_text(file_path: Path) -> str:
    """Extract text from Word documents."""
    try:
        from docx import Document
        doc = Document(str(file_path))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except ImportError:
        console.print("[yellow]DOCX support requires: pip install python-docx[/yellow]")
        return ""
    except Exception as e:
        console.print(f"[yellow]DOCX extraction failed: {e}[/yellow]")
        return ""


def extract_rtf_text(file_path: Path) -> str:
    """Extract text from RTF files."""
    try:
        from striprtf.striprtf import rtf_to_text
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return rtf_to_text(content)
    except ImportError:
        # Fallback: basic RTF stripping
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        # Remove RTF control words
        content = re.sub(r'\\[a-z]+\d*\s?', '', content)
        content = re.sub(r'[{}]', '', content)
        return content.strip()
    except Exception as e:
        console.print(f"[yellow]RTF extraction failed: {e}[/yellow]")
        return ""


def strip_latex_commands(latex: str) -> str:
    """Strip LaTeX commands and extract text."""
    # Remove comments
    latex = re.sub(r'%.*$', '', latex, flags=re.MULTILINE)
    # Remove common environments
    latex = re.sub(r'\\begin\{[^}]+\}', '', latex)
    latex = re.sub(r'\\end\{[^}]+\}', '', latex)
    # Remove commands with arguments
    latex = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', latex)
    # Remove commands without arguments
    latex = re.sub(r'\\[a-zA-Z]+', ' ', latex)
    # Remove special characters
    latex = re.sub(r'[{}$^_&~]', '', latex)
    # Clean up whitespace
    latex = re.sub(r'\s+', ' ', latex)
    return latex.strip()


def extract_csv_text(file_path: Path) -> str:
    """Convert CSV to readable text."""
    try:
        content = file_path.read_text(encoding="utf-8")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            return ""

        # Format as readable text
        headers = rows[0] if rows else []
        text_parts = []

        for row in rows[1:]:
            if row:
                row_text = ", ".join(f"{h}: {v}" for h, v in zip(headers, row) if v.strip())
                if row_text:
                    text_parts.append(row_text)

        return "\n".join(text_parts)
    except Exception as e:
        console.print(f"[yellow]CSV extraction failed: {e}[/yellow]")
        return ""


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

    # Find all supported files
    all_files = []
    for ext in SUPPORTED_EXTENSIONS:
        all_files.extend(f for f in VAULT_PATH.rglob(f"*{ext}") if should_index_file(f))
    # Remove duplicates (in case of overlapping patterns)
    all_files = list(set(all_files))

    stats = {"indexed": 0, "skipped": 0, "chunks": 0, "errors": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Indexing vault...", total=len(all_files))

        for file_path in all_files:
            try:
                content = extract_text(file_path)
                if not content.strip():
                    stats["skipped"] += 1
                    progress.advance(task)
                    continue
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
