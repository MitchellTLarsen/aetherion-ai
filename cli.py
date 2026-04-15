#!/usr/bin/env python3
"""
Aetherion AI - Writing and DM Assistant CLI

A semantic search and AI generation tool for the Aetherion world-building project.
"""
import sys
from pathlib import Path
from datetime import datetime

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.status import Status
from rich.live import Live

console = Console()


def _show_block(block_path: str, console: Console):
    """Show content of a specific block (file#header)."""
    from config import VAULT_PATH

    # Parse block path
    if "#" in block_path:
        file_path, header_slug = block_path.split("#", 1)
    else:
        file_path = block_path
        header_slug = None

    full_path = VAULT_PATH / file_path
    if not full_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    content = full_path.read_text(encoding="utf-8")

    if header_slug:
        # Find the section matching the header
        lines = content.split("\n")
        in_section = False
        section_lines = []
        target_header = header_slug.replace("-", " ").lower()

        for line in lines:
            if line.startswith("#"):
                current_header = line.lstrip("#").strip().lower()
                if current_header == target_header:
                    in_section = True
                    section_lines = [line]
                elif in_section:
                    # Hit a new header, stop
                    break
            elif in_section:
                section_lines.append(line)

        if section_lines:
            content = "\n".join(section_lines)
        else:
            console.print(f"[yellow]Header '{header_slug}' not found, showing full file[/yellow]")

    console.print(Panel(
        Markdown(content[:2000] + ("..." if len(content) > 2000 else "")),
        title=f"[bold]{block_path}[/bold]",
        border_style="blue"
    ))


def display_sources(sources: list[dict], console: Console):
    """Display source references with clickable Obsidian links."""
    from urllib.parse import quote
    from config import OBSIDIAN_VAULT_NAME

    if not sources:
        return

    console.print("\n[dim]─── Sources ───[/dim]")
    for i, src in enumerate(sources, 1):
        score_pct = src["score"] * 100
        color = "green" if score_pct > 70 else "yellow" if score_pct > 50 else "dim"
        header_part = f" > {src['header']}" if src.get("header") else ""

        # Build Obsidian link
        file_path = src['path']
        obsidian_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(file_path)}"

        # Rich link syntax: [link=URL]text[/link]
        console.print(f"[{color}]{i}. [link={obsidian_url}]{file_path}[/link]{header_part} ({score_pct:.0f}%)[/{color}]")
    console.print()


@click.group()
@click.version_option(version="2.0.0")
def cli():
    """Aetherion AI - Your writing and DM assistant for the world of Gryia."""
    pass


@cli.command()
@click.option("--force", "-f", is_flag=True, help="Force re-index all files")
def index(force: bool):
    """Index or update the vault embeddings."""
    from embeddings import index_vault, get_stats

    console.print("[bold blue]Indexing Aetherion vault...[/bold blue]\n")

    stats = index_vault(force=force)

    console.print(f"\n[green]Indexing complete![/green]")
    console.print(f"  Files indexed: {stats['indexed']}")
    console.print(f"  Files skipped (unchanged): {stats['skipped']}")
    console.print(f"  Total chunks created: {stats['chunks']}")
    if stats['errors'] > 0:
        console.print(f"  [red]Errors: {stats['errors']}[/red]")

    # Show total stats
    total_stats = get_stats()
    console.print(f"\n[dim]Database: {total_stats['total_files']} files, {total_stats['total_chunks']} chunks[/dim]")


@cli.command()
def stats():
    """Show vault index statistics."""
    from embeddings import get_stats
    from config import USE_RERANKER, RERANKER_MODEL

    s = get_stats()

    table = Table(title="Vault Index Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Files", str(s["total_files"]))
    table.add_row("Total Chunks", str(s["total_chunks"]))
    table.add_row("Embedding Provider", s.get("provider", "unknown"))
    table.add_row("Reranker", RERANKER_MODEL if USE_RERANKER else "disabled")
    table.add_row("Database Path", s["db_path"])

    console.print(table)


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Number of results")
@click.option("--filter", "-f", "file_filter", default=None, help="Filter by file path")
@click.option("--compact", "-c", is_flag=True, help="Compact output (paths only)")
@click.option("--no-rerank", is_flag=True, help="Disable reranking")
def search(query: str, limit: int, file_filter: str, compact: bool, no_rerank: bool):
    """Search the vault for relevant content."""
    from urllib.parse import quote
    from search import search as do_search
    from config import OBSIDIAN_VAULT_NAME

    with Status("[dim]Searching...[/dim]", console=console, spinner="dots"):
        results = do_search(query, n_results=limit, file_filter=file_filter, rerank=not no_rerank)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    console.print(f"\n[bold]Found {len(results)} results for:[/bold] {query}\n")

    if compact:
        for i, r in enumerate(results, 1):
            score_pct = r["score"] * 100
            color = "green" if score_pct > 70 else "yellow" if score_pct > 50 else "dim"

            block_ref = r['file_path']
            if r['header']:
                header_slug = r['header'].lower().replace(" ", "-")
                block_ref = f"{r['file_path']}#{header_slug}"

            # Clickable Obsidian link
            obsidian_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(r['file_path'])}"
            console.print(f"[{color}]{i}. [link={obsidian_url}]{block_ref}[/link] ({score_pct:.0f}%)[/{color}]")
        return

    for i, r in enumerate(results, 1):
        score_pct = r["score"] * 100
        color = "green" if score_pct > 70 else "yellow" if score_pct > 50 else "red"

        block_ref = r['file_path']
        if r['header']:
            header_slug = r['header'].lower().replace(" ", "-")
            block_ref = f"{r['file_path']}#{header_slug}"

        # Clickable Obsidian link in panel title
        obsidian_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(r['file_path'])}"
        console.print(Panel(
            r["content"][:500] + ("..." if len(r["content"]) > 500 else ""),
            title=f"[bold][link={obsidian_url}]{block_ref}[/link][/bold]",
            subtitle=f"[{color}]Score: {score_pct:.1f}%[/{color}]",
            border_style="dim"
        ))


@cli.command()
@click.argument("prompt")
@click.option("--provider", "-p", type=click.Choice(["openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"]), default=None)
@click.option("--no-context", is_flag=True, help="Don't use vault context")
@click.option("--context-size", "-c", default=5, help="Number of context chunks")
@click.option("--show-sources/--hide-sources", "-s/-S", default=True, help="Show/hide source references")
def ask(prompt: str, provider: str, no_context: bool, context_size: int, show_sources: bool):
    """Ask a question about the world or generate content."""
    from config import DEFAULT_PROVIDER
    from generate import generate_with_gemini, generate_with_gpt

    provider = provider or DEFAULT_PROVIDER
    console.print(f"\n[dim]Using {provider} with {'no' if no_context else context_size} context chunks...[/dim]\n")

    with Status("[dim]Generating...[/dim]", console=console, spinner="dots"):
        if provider == "gemini":
            response, sources = generate_with_gemini(
                prompt,
                use_vault_context=not no_context,
                n_context=context_size,
                return_sources=True
            )
        else:
            response, sources = generate_with_gpt(
                prompt,
                use_vault_context=not no_context,
                n_context=context_size,
                return_sources=True
            )

    if show_sources and not no_context and sources:
        display_sources(sources, console)

    console.print(Markdown(response))


@cli.command()
@click.argument("file_path")
@click.option("--aspect", "-a", default=None, help="Specific aspect to expand on")
@click.option("--provider", "-p", type=click.Choice(["openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"]), default=None)
def expand(file_path: str, aspect: str, provider: str):
    """Expand on an existing note with AI-generated content."""
    from config import DEFAULT_PROVIDER
    from generate import expand_note

    provider = provider or DEFAULT_PROVIDER
    console.print(f"\n[dim]Expanding {file_path} with {provider}...[/dim]\n")

    with Status("[dim]Generating...[/dim]", console=console, spinner="dots"):
        response = expand_note(file_path, aspect=aspect, provider=provider)

    console.print(Markdown(response))


@cli.command()
@click.argument("location")
@click.option("--level", "-l", default=5, help="Party level")
@click.option("--difficulty", "-d", type=click.Choice(["easy", "medium", "hard", "deadly"]), default="medium")
@click.option("--themes", "-t", multiple=True, help="Encounter themes")
@click.option("--provider", "-p", type=click.Choice(["openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"]), default=None)
def encounter(location: str, level: int, difficulty: str, themes: tuple, provider: str):
    """Generate a D&D encounter for a location."""
    from config import DEFAULT_PROVIDER
    from generate import generate_encounter

    provider = provider or DEFAULT_PROVIDER
    console.print(f"\n[dim]Generating encounter for {location} with {provider}...[/dim]\n")

    with Status("[dim]Generating...[/dim]", console=console, spinner="dots"):
        response = generate_encounter(
            location=location,
            party_level=level,
            difficulty=difficulty,
            themes=list(themes) if themes else None,
            provider=provider
        )

    console.print(Markdown(response))


@cli.command()
@click.argument("location")
@click.option("--role", "-r", default=None, help="NPC role (e.g., merchant, guard, noble)")
@click.option("--provider", "-p", type=click.Choice(["openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"]), default=None)
def npc(location: str, role: str, provider: str):
    """Generate an NPC for a location."""
    from config import DEFAULT_PROVIDER
    from generate import generate_npc

    provider = provider or DEFAULT_PROVIDER
    console.print(f"\n[dim]Generating NPC for {location} with {provider}...[/dim]\n")

    with Status("[dim]Generating...[/dim]", console=console, spinner="dots"):
        response = generate_npc(location=location, role=role, provider=provider)

    console.print(Markdown(response))


@cli.command()
@click.option("--provider", "-p", type=click.Choice(["openai", "gpt", "gemini", "anthropic", "claude", "ollama", "groq", "openrouter"]), default=None)
@click.option("--show-sources/--hide-sources", "-s/-S", default=True, help="Show/hide source references")
@click.option("--confirm/--no-confirm", default=True, help="Confirm before sending to LLM")
@click.option("--stream/--no-stream", default=True, help="Stream responses")
@click.option("--load", "-l", "session_name", default=None, help="Load a saved chat session")
def chat(provider: str, show_sources: bool, confirm: bool, stream: bool, session_name: str):
    """Start an interactive chat session about the world."""
    from config import DEFAULT_PROVIDER, SYSTEM_PROMPT
    from generate import (
        get_context_only, chat_with_context, chat_with_context_stream,
        save_chat_history, load_chat_history, list_chat_sessions,
        multi_query_context, compress_context
    )

    provider = provider or DEFAULT_PROVIDER

    # Load existing session if specified
    history = []
    sources_log = []
    custom_prompt = SYSTEM_PROMPT

    if session_name:
        history, sources_log = load_chat_history(session_name)
        if history:
            console.print(f"[green]Loaded session '{session_name}' with {len(history)//2} messages[/green]")
        else:
            console.print(f"[yellow]No session '{session_name}' found, starting fresh[/yellow]")

    console.print(Panel(
        "[bold]Welcome to Aetherion AI Chat[/bold]\n\n"
        "Ask questions about the world of Gryia, get help with world-building,\n"
        "or plan your D&D sessions. Type 'quit' or 'exit' to end.\n\n"
        "Commands:\n"
        "  /sources      - toggle source display\n"
        "  /confirm      - toggle confirm-before-send\n"
        "  /stream       - toggle streaming\n"
        "  /cost         - show detailed cost breakdown\n"
        "  /open <path>  - view a block\n"
        "  /save <name>  - save chat session\n"
        "  /load <name>  - load chat session\n"
        "  /list         - list saved sessions\n"
        "  /clear        - clear history\n"
        "  /prompt       - set custom system prompt\n"
        "  /deep         - use multi-query + compression\n\n"
        f"[dim]Using: {provider} | Sources: {'on' if show_sources else 'off'} | "
        f"Confirm: {'on' if confirm else 'off'} | Stream: {'on' if stream else 'off'}[/dim]",
        title="Aetherion",
        border_style="blue"
    ))

    context_size = 20
    use_deep_search = False

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.lower() in ["quit", "exit", "q"]:
            break

        if not user_input.strip():
            continue

        # Handle commands
        if user_input.strip() == "/sources":
            show_sources = not show_sources
            console.print(f"[dim]Sources: {'on' if show_sources else 'off'}[/dim]")
            continue

        if user_input.strip() == "/confirm":
            confirm = not confirm
            console.print(f"[dim]Confirm before send: {'on' if confirm else 'off'}[/dim]")
            continue

        if user_input.strip() == "/stream":
            stream = not stream
            console.print(f"[dim]Streaming: {'on' if stream else 'off'}[/dim]")
            continue

        if user_input.strip() == "/deep":
            use_deep_search = not use_deep_search
            console.print(f"[dim]Deep search (multi-query + compression): {'on' if use_deep_search else 'off'}[/dim]")
            continue

        if user_input.strip() == "/cost":
            from costs import PRICING, get_model_for_provider
            model = get_model_for_provider(provider)
            pricing = PRICING.get(model, {"input": "unknown", "output": "unknown"})
            console.print(f"\n[bold]Cost Info for {provider}[/bold]")
            console.print(f"  Model: {model}")
            if pricing["input"] == 0:
                console.print(f"  Pricing: [green]FREE[/green] (local or free tier)")
            else:
                console.print(f"  Input: ${pricing['input']:.2f} / 1M tokens")
                console.print(f"  Output: ${pricing['output']:.2f} / 1M tokens")
            console.print()
            continue

        if user_input.strip().startswith("/open "):
            block_path = user_input.strip()[6:].strip()
            _show_block(block_path, console)
            continue

        if user_input.strip().startswith("/save "):
            name = user_input.strip()[6:].strip() or f"session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            save_chat_history(name, history, sources_log)
            console.print(f"[green]Saved session as '{name}'[/green]")
            continue

        if user_input.strip().startswith("/load "):
            name = user_input.strip()[6:].strip()
            history, sources_log = load_chat_history(name)
            if history:
                console.print(f"[green]Loaded session '{name}' with {len(history)//2} messages[/green]")
            else:
                console.print(f"[yellow]Session '{name}' not found[/yellow]")
            continue

        if user_input.strip() == "/list":
            sessions = list_chat_sessions()
            if sessions:
                console.print("[bold]Saved sessions:[/bold]")
                for s in sessions:
                    console.print(f"  - {s}")
            else:
                console.print("[dim]No saved sessions[/dim]")
            continue

        if user_input.strip() == "/clear":
            history = []
            sources_log = []
            console.print("[dim]History cleared[/dim]")
            continue

        if user_input.strip() == "/prompt":
            console.print("[dim]Enter new system prompt (or 'reset' for default):[/dim]")
            new_prompt = Prompt.ask("")
            if new_prompt.lower() == "reset":
                custom_prompt = SYSTEM_PROMPT
                console.print("[dim]Reset to default prompt[/dim]")
            else:
                custom_prompt = new_prompt
                console.print("[dim]Custom prompt set[/dim]")
            continue

        # Step 1: Search for context
        console.print()
        with Status(f"[dim]Searching vault...[/dim]", console=console, spinner="dots"):
            if use_deep_search:
                sources = multi_query_context(user_input, n_results=context_size)
                sources = compress_context(sources)
            else:
                sources = get_context_only(user_input, n_results=context_size)

        if not sources:
            console.print("[yellow]No relevant context found in vault.[/yellow]")
        else:
            console.print(f"[dim]Found {len(sources)} relevant chunks:[/dim]")
            if show_sources:
                display_sources(sources, console)

        # Calculate and show token count / cost estimate
        from costs import estimate_chat_cost, format_cost, get_model_for_provider
        context_text = "\n".join([s.get("content", "") for s in (sources or [])])
        model = get_model_for_provider(provider)
        cost_estimate = estimate_chat_cost(
            messages=history + [{"role": "user", "content": user_input}],
            system_prompt=custom_prompt,
            context=context_text,
            model=model
        )
        console.print(f"[dim]Estimated: {format_cost(cost_estimate)}[/dim]")

        # Step 2: Confirm before sending (if enabled)
        if confirm:
            while True:
                action = Prompt.ask(
                    "[dim]Send to LLM?[/dim]",
                    choices=["y", "n", "more", "open", "skip"],
                    default="y"
                )

                if action == "y":
                    break
                elif action == "n" or action == "skip":
                    console.print("[dim]Skipped.[/dim]")
                    sources = None
                    break
                elif action == "more":
                    context_size += 5
                    with Status(f"[dim]Fetching {context_size} chunks...[/dim]", console=console, spinner="dots"):
                        if use_deep_search:
                            sources = multi_query_context(user_input, n_results=context_size)
                            sources = compress_context(sources)
                        else:
                            sources = get_context_only(user_input, n_results=context_size)
                    display_sources(sources, console)
                elif action == "open":
                    if sources:
                        idx = Prompt.ask("[dim]Which source # to view?[/dim]", default="1")
                        try:
                            src = sources[int(idx) - 1]
                            _show_block(src["block"], console)
                        except (ValueError, IndexError):
                            console.print("[red]Invalid source number[/red]")

            if sources is None:
                continue

        # Step 3: Send to LLM
        if stream:
            # Streaming response - show thinking status until first chunk
            console.print()
            with Status(f"[bold blue]Thinking...[/bold blue] [dim]({provider})[/dim]", console=console, spinner="dots") as status:
                stream_gen = chat_with_context_stream(
                    user_input,
                    sources=sources or [],
                    history=history,
                    provider=provider,
                    system_prompt=custom_prompt
                )
                # Get first chunk to clear the status
                first_chunk = next(stream_gen, "")
                status.stop()

            console.print("[bold green]Aetherion[/bold green]")
            full_response = first_chunk
            with Live(Markdown(full_response), console=console, refresh_per_second=10) as live:
                for chunk in stream_gen:
                    full_response += chunk
                    live.update(Markdown(full_response))
            response = full_response
        else:
            # Non-streaming response
            console.print()
            with Status(f"[bold blue]Thinking...[/bold blue] [dim]({provider})[/dim]", console=console, spinner="dots"):
                response = chat_with_context(
                    user_input,
                    sources=sources or [],
                    history=history,
                    provider=provider,
                    system_prompt=custom_prompt
                )
            console.print("[bold green]Aetherion[/bold green]")
            console.print(Markdown(response))

        # Update history
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        sources_log.append(sources or [])

        # Reset context size for next query
        context_size = 20

    console.print("\n[dim]Farewell, traveler.[/dim]")


@cli.command()
@click.argument("file_path")
@click.option("--limit", "-n", default=5, help="Number of related notes")
def related(file_path: str, limit: int):
    """Find notes related to a given note."""
    from search import find_related

    results = find_related(file_path, n_results=limit)

    if not results:
        console.print("[yellow]No related notes found.[/yellow]")
        return

    console.print(f"\n[bold]Notes related to:[/bold] {file_path}\n")

    table = Table()
    table.add_column("Block", style="cyan")
    table.add_column("Score", style="green")

    for r in results:
        score_pct = r["score"] * 100
        block_ref = r['file_path']
        if r['header']:
            header_slug = r['header'].lower().replace(" ", "-")
            block_ref = f"{r['file_path']}#{header_slug}"
        table.add_row(block_ref, f"{score_pct:.1f}%")

    console.print(table)


@cli.command()
@click.argument("file_path")
@click.option("--limit", "-n", default=10, help="Number of connections")
def connections(file_path: str, limit: int):
    """Show smart connections for a note (like Smart Connections plugin)."""
    from urllib.parse import quote
    from search import find_related
    from config import VAULT_PATH, OBSIDIAN_VAULT_NAME

    full_path = VAULT_PATH / file_path
    if not full_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    # Get note title
    note_name = full_path.stem

    with Status("[dim]Finding connections...[/dim]", console=console, spinner="dots"):
        results = find_related(file_path, n_results=limit)

    if not results:
        console.print("[yellow]No connections found.[/yellow]")
        return

    # Display like Smart Connections
    console.print()
    obsidian_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(file_path)}"
    console.print(Panel(
        f"[bold][link={obsidian_url}]{note_name}[/link][/bold]\n[dim]{file_path}[/dim]",
        title="Smart Connections",
        border_style="blue"
    ))

    console.print()

    for i, r in enumerate(results, 1):
        score_pct = r["score"] * 100

        # Color based on relevance
        if score_pct >= 70:
            bar = "[green]████████████████████[/green]"
            color = "green"
        elif score_pct >= 50:
            bar_len = int(score_pct / 5)
            bar = f"[yellow]{'█' * bar_len}{'░' * (20 - bar_len)}[/yellow]"
            color = "yellow"
        else:
            bar_len = int(score_pct / 5)
            bar = f"[dim]{'█' * bar_len}{'░' * (20 - bar_len)}[/dim]"
            color = "dim"

        # Get note name
        related_name = Path(r['file_path']).stem
        header_part = f" › {r['header']}" if r.get('header') else ""

        # Clickable Obsidian link
        related_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(r['file_path'])}"

        console.print(f"{bar} [{color}]{score_pct:.0f}%[/{color}]")
        console.print(f"   [bold][link={related_url}]{related_name}[/link][/bold]{header_part}")
        console.print(f"   [dim]{r['file_path']}[/dim]")
        console.print()


@cli.command()
@click.argument("block_path")
def block(block_path: str):
    """View a specific block/section from a note.

    Use file.md#header-name format to view a specific section.
    Example: aetherion block "Database/Locations/Tavern.md#history"
    """
    _show_block(block_path, console)


@cli.command()
def sessions():
    """List saved chat sessions."""
    from generate import list_chat_sessions

    sessions = list_chat_sessions()
    if sessions:
        console.print("[bold]Saved chat sessions:[/bold]")
        for s in sessions:
            console.print(f"  - {s}")
    else:
        console.print("[dim]No saved sessions[/dim]")


@cli.command()
def providers():
    """List available AI providers and their status."""
    from providers import available_providers

    console.print("\n[bold]AI Providers[/bold]\n")

    table = Table()
    table.add_column("Provider", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Default Model", style="dim")

    for p in available_providers():
        status = "[green]Available[/green]" if p["available"] else "[red]Not configured[/red]"
        table.add_row(p["name"], status, p["default_model"])

    console.print(table)
    console.print("\n[dim]Configure providers by adding API keys to .env[/dim]")
    console.print("[dim]Use -p/--provider flag to select: e.g., chat -p anthropic[/dim]")


@cli.command()
def watch():
    """Watch vault for changes and auto-reindex."""
    import time
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    from config import VAULT_PATH, INCLUDE_FOLDERS
    from embeddings import index_vault

    class VaultHandler(FileSystemEventHandler):
        def __init__(self):
            self.pending_reindex = False
            self.last_event = 0

        def on_any_event(self, event):
            # Skip non-markdown files
            if not event.src_path.endswith('.md'):
                return

            # Skip hidden folders
            if '/.' in event.src_path:
                return

            # Only watch included folders
            in_included = any(f"/{folder}/" in event.src_path for folder in INCLUDE_FOLDERS)
            if not in_included:
                return

            # Debounce - wait for changes to settle
            self.pending_reindex = True
            self.last_event = time.time()

    handler = VaultHandler()
    observer = Observer()
    observer.schedule(handler, str(VAULT_PATH), recursive=True)
    observer.start()

    console.print(f"[bold blue]Watching vault for changes...[/bold blue]")
    console.print(f"[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            time.sleep(1)
            # If changes pending and no new events for 2 seconds, reindex
            if handler.pending_reindex and (time.time() - handler.last_event > 2):
                console.print(f"[dim]{datetime.now().strftime('%H:%M:%S')} - Changes detected, reindexing...[/dim]")
                try:
                    stats = index_vault(force=False)
                    if stats['indexed'] > 0:
                        console.print(f"[green]Indexed {stats['indexed']} files, {stats['chunks']} chunks[/green]")
                    else:
                        console.print(f"[dim]No changes to index[/dim]")
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                handler.pending_reindex = False
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[dim]Stopped watching.[/dim]")

    observer.join()


# =============================================================================
# WORLD-BUILDING TOOLS
# =============================================================================

@cli.command()
@click.argument("content")
@click.option("--file", "-f", "file_path", default=None, help="File to check against (optional)")
def check(content: str, file_path: str):
    """Check new content for consistency with existing lore.

    Example: aetherion check "The Stormborn worship fire gods"
    """
    from config import DEFAULT_PROVIDER, SYSTEM_PROMPT
    from generate import get_context_only, chat_with_context

    console.print("\n[bold]Consistency Check[/bold]\n")

    # Get relevant context
    with Status("[dim]Finding related lore...[/dim]", console=console, spinner="dots"):
        sources = get_context_only(content, n_results=15)

    if not sources:
        console.print("[yellow]No related lore found to check against.[/yellow]")
        return

    display_sources(sources, console)

    # Build check prompt
    check_prompt = f"""I want to add this new content to my world:

"{content}"

Based on the existing lore provided in the context, analyze this for consistency:

1. **Contradictions**: Does this contradict any established facts? List specific conflicts.
2. **Consistency**: Does this fit with the tone, naming conventions, and established patterns?
3. **Connections**: What existing elements does this relate to or build upon?
4. **Suggestions**: How could this be improved to better fit the world?

Be specific and cite the relevant sources."""

    with Status("[dim]Analyzing consistency...[/dim]", console=console, spinner="dots"):
        response = chat_with_context(
            check_prompt,
            sources=sources,
            provider=DEFAULT_PROVIDER,
            system_prompt=SYSTEM_PROMPT
        )

    console.print(Panel(Markdown(response), title="Analysis", border_style="blue"))


@cli.command()
@click.argument("entity")
def refs(entity: str):
    """Find all references to an entity across the vault.

    Example: aetherion refs "Stormborn"
    """
    from urllib.parse import quote
    from search import search
    from config import VAULT_PATH, OBSIDIAN_VAULT_NAME

    console.print(f"\n[bold]References to:[/bold] {entity}\n")

    with Status("[dim]Searching...[/dim]", console=console, spinner="dots"):
        results = search(entity, n_results=30, rerank=False)

    if not results:
        console.print("[yellow]No references found.[/yellow]")
        return

    # Group by file
    by_file = {}
    for r in results:
        fp = r['file_path']
        if fp not in by_file:
            by_file[fp] = []
        by_file[fp].append(r)

    console.print(f"Found in [green]{len(by_file)}[/green] files:\n")

    for fp, file_refs in by_file.items():
        # Clickable Obsidian link
        obsidian_url = f"obsidian://open?vault={quote(OBSIDIAN_VAULT_NAME)}&file={quote(fp)}"
        console.print(f"[bold cyan][link={obsidian_url}]{fp}[/link][/bold cyan]")
        for ref in file_refs:
            header = f" › {ref['header']}" if ref.get('header') else ""
            score = ref['score'] * 100
            console.print(f"  [dim]{score:.0f}%[/dim]{header}")
        console.print()


@cli.command()
@click.option("--folder", "-f", default=None, help="Check specific folder")
def gaps(folder: str):
    """Find underdeveloped areas in the world.

    Analyzes notes to find stubs, missing information, and areas needing expansion.
    """
    from config import VAULT_PATH, INCLUDE_FOLDERS, DEFAULT_PROVIDER
    from generate import chat_with_context, get_context_only

    console.print("\n[bold]Gap Analysis[/bold]\n")

    # Find all notes
    folders_to_check = [folder] if folder else INCLUDE_FOLDERS
    stubs = []
    all_notes = []

    with Status("[dim]Scanning vault...[/dim]", console=console, spinner="dots"):
        for folder_name in folders_to_check:
            folder_path = VAULT_PATH / folder_name
            if not folder_path.exists():
                continue

            for md_file in folder_path.rglob("*.md"):
                if md_file.name.startswith("."):
                    continue

                content = md_file.read_text(encoding="utf-8")
                rel_path = str(md_file.relative_to(VAULT_PATH))
                word_count = len(content.split())

                all_notes.append({
                    "path": rel_path,
                    "name": md_file.stem,
                    "words": word_count,
                    "content": content[:500]
                })

                # Flag as stub if very short
                if word_count < 100:
                    stubs.append({
                        "path": rel_path,
                        "name": md_file.stem,
                        "words": word_count
                    })

    # Show stubs
    if stubs:
        console.print(f"[yellow]Stub notes ({len(stubs)} files < 100 words):[/yellow]\n")
        table = Table()
        table.add_column("Note", style="cyan")
        table.add_column("Words", style="yellow")
        table.add_column("Path", style="dim")

        for stub in sorted(stubs, key=lambda x: x['words']):
            table.add_row(stub['name'], str(stub['words']), stub['path'])

        console.print(table)
        console.print()

    # Ask AI to analyze for gaps
    console.print("[bold]Analyzing for missing content...[/bold]\n")

    notes_summary = "\n".join([f"- {n['name']} ({n['words']} words)" for n in all_notes[:50]])

    gap_prompt = f"""Analyze this world-building project for gaps and underdeveloped areas.

Here are the existing notes:
{notes_summary}

Based on typical fantasy world-building needs, identify:

1. **Missing Categories**: What typical world elements are missing? (e.g., economy, magic system, calendar, languages)
2. **Underdeveloped Areas**: Which existing topics need more depth?
3. **Missing Connections**: What relationships between existing elements should be defined?
4. **Suggested Additions**: What specific notes should be created?

Be specific and actionable."""

    with Status("[dim]Analyzing gaps...[/dim]", console=console, spinner="dots"):
        sources = get_context_only("world overview kingdoms religions characters", n_results=10)
        response = chat_with_context(
            gap_prompt,
            sources=sources,
            provider=DEFAULT_PROVIDER
        )

    console.print(Panel(Markdown(response), title="Gap Analysis", border_style="yellow"))


@cli.command()
@click.argument("file_path")
@click.option("--save", "-s", is_flag=True, help="Save expanded content to file")
def lore(file_path: str, save: bool):
    """Expand a stub note with AI-generated lore.

    Takes a short note and fleshes it out based on related lore.
    """
    from config import VAULT_PATH, DEFAULT_PROVIDER, SYSTEM_PROMPT
    from generate import get_context_only, chat_with_context
    from search import find_related

    full_path = VAULT_PATH / file_path
    if not full_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    content = full_path.read_text(encoding="utf-8")
    note_name = full_path.stem

    console.print(f"\n[bold]Expanding:[/bold] {note_name}\n")
    console.print(f"[dim]Current content ({len(content.split())} words):[/dim]")
    console.print(Panel(content[:500] + ("..." if len(content) > 500 else ""), border_style="dim"))

    # Get related context
    with Status("[dim]Finding related lore...[/dim]", console=console, spinner="dots"):
        sources = find_related(file_path, n_results=15)

    if sources:
        console.print(f"\n[dim]Using {len(sources)} related notes for context[/dim]")

    # Generate expansion
    expand_prompt = f"""Expand this world-building note with rich, detailed lore.

Current note "{note_name}":
{content}

Based on the related lore in the context, write an expanded version that:
1. Maintains consistency with established facts
2. Adds depth: history, culture, notable features, connections to other elements
3. Includes specific details: names, dates, descriptions
4. Matches the tone and style of the existing content
5. References and connects to other known elements of the world

Write the expanded content in markdown format, ready to replace the current note."""

    with Status("[dim]Generating expanded lore...[/dim]", console=console, spinner="dots"):
        # Convert find_related results to source format
        formatted_sources = [{
            "path": r["file_path"],
            "block": r["file_path"],
            "header": r.get("header", ""),
            "score": r["score"],
            "content": r["content"]
        } for r in sources]

        response = chat_with_context(
            expand_prompt,
            sources=formatted_sources,
            provider=DEFAULT_PROVIDER,
            system_prompt=SYSTEM_PROMPT
        )

    console.print("\n[bold green]Expanded Content:[/bold green]\n")
    console.print(Panel(Markdown(response), border_style="green"))

    if save:
        # Backup original
        backup_path = full_path.with_suffix(".md.bak")
        backup_path.write_text(content, encoding="utf-8")
        console.print(f"[dim]Backup saved to: {backup_path}[/dim]")

        # Save new content
        full_path.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to: {file_path}[/green]")
    else:
        console.print("\n[dim]Use --save to write this to the file[/dim]")


@cli.command()
@click.option("--file", "-f", "file_path", default=None, help="Timeline file to check")
def timeline(file_path: str):
    """Validate timeline consistency across the world.

    Checks for chronological contradictions and gaps.
    """
    from config import VAULT_PATH, DEFAULT_PROVIDER
    from generate import get_context_only, chat_with_context

    console.print("\n[bold]Timeline Validation[/bold]\n")

    # Try to find timeline file
    if file_path:
        timeline_path = VAULT_PATH / file_path
    else:
        timeline_path = VAULT_PATH / "Timeline.md"

    timeline_content = ""
    if timeline_path.exists():
        timeline_content = timeline_path.read_text(encoding="utf-8")
        console.print(f"[dim]Found timeline: {timeline_path.name}[/dim]\n")

    # Get all temporal references
    with Status("[dim]Gathering temporal references...[/dim]", console=console, spinner="dots"):
        sources = get_context_only(
            "history timeline year age era founded established before after during ancient",
            n_results=25
        )

    if not sources:
        console.print("[yellow]No temporal references found.[/yellow]")
        return

    display_sources(sources, console)

    # Analyze timeline
    validate_prompt = f"""Analyze the timeline and temporal references in this world for consistency.

{"Main Timeline:" + chr(10) + timeline_content[:2000] if timeline_content else "No main timeline file found."}

Based on all the temporal references in the context, check for:

1. **Contradictions**: Events that conflict chronologically
2. **Impossible Sequences**: Things that happened "before" events they depend on
3. **Age Conflicts**: Characters or entities with inconsistent ages/lifespans
4. **Era Mismatches**: Events placed in wrong historical periods
5. **Gaps**: Missing time periods or unexplained jumps

Create a timeline summary and flag any issues found. Be specific with dates/eras mentioned."""

    with Status("[dim]Validating timeline...[/dim]", console=console, spinner="dots"):
        response = chat_with_context(
            validate_prompt,
            sources=sources,
            provider=DEFAULT_PROVIDER
        )

    console.print(Panel(Markdown(response), title="Timeline Analysis", border_style="blue"))


@cli.command()
@click.argument("file_path")
@click.option("--save", "-s", is_flag=True, help="Save to file (creates backup)")
@click.option("--template", "-t", default=None, help="Override template to use")
@click.option("--no-check", is_flag=True, help="Skip consistency check")
def flesh(file_path: str, save: bool, template: str, no_check: bool):
    """Flesh out a note based on its template structure.

    Reads the note, identifies its type, loads the template, and expands
    each section with AI-generated content based on existing lore.

    Automatically:
    - Cross-references related notes for context
    - Checks timeline for temporal consistency
    - Validates against existing lore for contradictions
    - Uses established names, factions, and relationships

    Example: aetherion flesh "Database/Kingdoms/MyKingdom.md" --save
    """
    import re
    import yaml
    from config import VAULT_PATH, DEFAULT_PROVIDER, SYSTEM_PROMPT
    from generate import chat_with_context, get_context_only
    from search import find_related, search

    full_path = VAULT_PATH / file_path
    if not full_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        return

    content = full_path.read_text(encoding="utf-8")
    note_name = full_path.stem

    console.print(f"\n[bold]Fleshing out:[/bold] {note_name}\n")

    # Parse frontmatter
    frontmatter = {}
    frontmatter_raw = ""
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_raw = f"---{parts[1]}---"
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except:
                pass
            body = parts[2]

    # Detect note type
    note_type = None
    if template:
        note_type = template
    elif frontmatter.get("NoteIcon"):
        note_type = frontmatter["NoteIcon"]
    elif frontmatter.get("tags"):
        tags = frontmatter["tags"]
        if isinstance(tags, list) and tags:
            note_type = tags[0]

    console.print(f"[dim]Detected type: {note_type or 'unknown'}[/dim]")

    # Find template
    template_path = None
    templates_dir = VAULT_PATH / "Templates"
    if note_type and templates_dir.exists():
        for t in templates_dir.glob("Template - *.md"):
            if note_type.lower() in t.stem.lower():
                template_path = t
                break

    # Get template headings
    template_headings = []
    if template_path:
        template_content = template_path.read_text(encoding="utf-8")
        template_headings = re.findall(r'^##+ (.+)$', template_content, re.MULTILINE)
        console.print(f"[dim]Using template: {template_path.name}[/dim]")

    # Extract current headings and content from note
    current_sections = {}
    current_heading = "_intro"
    current_content = []

    for line in body.split("\n"):
        if line.startswith("## "):
            if current_content:
                current_sections[current_heading] = "\n".join(current_content).strip()
            current_heading = line.lstrip("#").strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        current_sections[current_heading] = "\n".join(current_content).strip()

    # Find what's already filled vs empty
    filled = {k: v for k, v in current_sections.items() if v and len(v.strip()) > 50}
    empty = {k: v for k, v in current_sections.items() if not v or len(v.strip()) <= 50}

    console.print(f"[green]Filled sections ({len(filled)}):[/green] {', '.join(list(filled.keys())[:5]) or 'none'}")
    console.print(f"[yellow]Empty sections ({len(empty)}):[/yellow] {', '.join(list(empty.keys())[:5]) or 'none'}")

    if not empty and not template_headings:
        console.print("\n[green]Note appears to be complete![/green]")
        return

    # =========================================================================
    # GATHER COMPREHENSIVE CONTEXT
    # =========================================================================

    console.print(f"\n[bold]Gathering context for continuity...[/bold]")

    # 1. Related notes
    with Status("[dim]1/4 Finding related notes...[/dim]", console=console, spinner="dots"):
        related = find_related(file_path, n_results=20)
    console.print(f"  [dim]Found {len(related)} related notes[/dim]")

    # 2. Timeline context
    timeline_context = ""
    timeline_path = VAULT_PATH / "Timeline.md"
    with Status("[dim]2/4 Loading timeline...[/dim]", console=console, spinner="dots"):
        if timeline_path.exists():
            timeline_content = timeline_path.read_text(encoding="utf-8")
            # Extract relevant timeline entries mentioning this note or related terms
            timeline_context = timeline_content[:3000]
    console.print(f"  [dim]Timeline loaded[/dim]")

    # 3. Cross-references - find what mentions this entity
    with Status("[dim]3/4 Finding cross-references...[/dim]", console=console, spinner="dots"):
        cross_refs = search(note_name, n_results=15, rerank=False)
        # Filter out self-references
        cross_refs = [r for r in cross_refs if r['file_path'] != file_path]
    console.print(f"  [dim]Found {len(cross_refs)} cross-references[/dim]")

    # 4. Get frontmatter relationships
    linked_entities = []
    with Status("[dim]4/4 Resolving relationships...[/dim]", console=console, spinner="dots"):
        for key in ['Rulers', 'Leaders', 'AssociatedKingdom', 'Religions', 'Groups', 'CurrentLocation']:
            if frontmatter.get(key):
                val = frontmatter[key]
                if isinstance(val, list):
                    linked_entities.extend(val)
                elif val:
                    linked_entities.append(val)

        # Get context for linked entities
        linked_context = []
        for entity in linked_entities[:5]:
            entity_results = search(str(entity), n_results=2, rerank=False)
            for r in entity_results:
                linked_context.append(f"About {entity} (from {r['file_path']}):\n{r['content'][:300]}")
    console.print(f"  [dim]Resolved {len(linked_entities)} linked entities[/dim]")

    # Determine sections to flesh out
    sections_to_flesh = list(empty.keys())
    if template_headings:
        for h in template_headings:
            if h not in current_sections and h not in sections_to_flesh:
                sections_to_flesh.append(h)

    # Remove _intro from sections to generate
    sections_to_flesh = [s for s in sections_to_flesh if s != "_intro"]

    if not sections_to_flesh:
        console.print("\n[green]All sections filled![/green]")
        return

    console.print(f"\n[bold]Generating {len(sections_to_flesh)} sections with full context...[/bold]\n")

    # Build comprehensive context
    existing_content = "\n\n".join([f"### {k}\n{v}" for k, v in filled.items() if k != "_intro"])
    intro_content = current_sections.get("_intro", "")

    # Extract clean intro
    intro_lines = []
    for line in intro_content.split("\n"):
        if line.startswith("> [!") or line.startswith("> ```") or line.startswith(">"):
            continue
        if "```" in line:
            continue
        if line.strip():
            intro_lines.append(line)
    clean_intro = "\n".join(intro_lines[:20])

    # Build related lore context
    related_context = []
    for r in related[:10]:
        related_context.append(f"From {r['file_path']}:\n{r['content'][:400]}")

    # Build cross-reference context
    crossref_context = []
    for r in cross_refs[:8]:
        crossref_context.append(f"Mentioned in {r['file_path']}:\n{r['content'][:300]}")

    sections_list = "\n".join([f"- {s}" for s in sections_to_flesh])

    # =========================================================================
    # ENHANCED PROMPT WITH CONTINUITY INSTRUCTIONS
    # =========================================================================

    flesh_prompt = f"""You are expanding a world-building note for "{note_name}" (type: {note_type or 'unknown'}).

CRITICAL: Maintain absolute consistency with existing lore. Cross-reference all details.

=== EXISTING CONTENT IN THIS NOTE ===
{clean_intro}

{existing_content if existing_content else "(No sections filled yet)"}

=== FRONTMATTER RELATIONSHIPS ===
{', '.join([f'{k}: {frontmatter.get(k)}' for k in ['Rulers', 'Leaders', 'AssociatedKingdom', 'Religions', 'Groups'] if frontmatter.get(k)])}

=== SECTIONS TO WRITE ===
{sections_list}

=== RELATED LORE (maintain consistency with these) ===
{chr(10).join(related_context[:6])}

=== HOW THIS IS REFERENCED ELSEWHERE ===
{chr(10).join(crossref_context[:4]) if crossref_context else "(No external references found)"}

=== LINKED ENTITIES CONTEXT ===
{chr(10).join(linked_context[:3]) if linked_context else "(No linked entities)"}

=== TIMELINE CONTEXT ===
{timeline_context[:1500] if timeline_context else "(No timeline found)"}

=== WRITING INSTRUCTIONS ===
For each section, you MUST:
1. USE established names, titles, and terminology from the context
2. REFERENCE existing characters, locations, and factions by their correct names
3. ALIGN with timeline - use correct eras, dates, and historical sequences
4. CONNECT to other elements mentioned in related notes
5. MAINTAIN the existing tone and writing style
6. AVOID contradicting any established facts
7. ADD specific details: names, dates, descriptions, relationships
8. CREATE hooks and connections to other parts of the world

If the context mentions specific details (rulers, dates, events), USE them exactly.
If creating new elements, ensure they fit logically with what exists.

Format your response as:
## Section Name
Content here...

## Next Section
Content here...

Only write the sections listed above. Be thorough, detailed, and consistent."""

    # Convert to source format
    all_sources = [{
        "path": r["file_path"],
        "block": r["file_path"],
        "header": r.get("header", ""),
        "score": r["score"],
        "content": r["content"]
    } for r in (related + cross_refs)[:25]]

    with Status("[dim]Generating content with full context...[/dim]", console=console, spinner="dots"):
        response = chat_with_context(
            flesh_prompt,
            sources=all_sources,
            provider=DEFAULT_PROVIDER,
            system_prompt=SYSTEM_PROMPT
        )

    # Parse generated sections
    generated_sections = {}
    current_section = None
    section_content = []

    for line in response.split("\n"):
        if line.startswith("## "):
            if current_section and section_content:
                generated_sections[current_section] = "\n".join(section_content).strip()
            current_section = line.lstrip("#").strip()
            section_content = []
        elif current_section:
            section_content.append(line)

    if current_section and section_content:
        generated_sections[current_section] = "\n".join(section_content).strip()

    console.print(f"[green]Generated {len(generated_sections)} sections[/green]\n")

    # =========================================================================
    # CONSISTENCY CHECK
    # =========================================================================

    if not no_check and generated_sections:
        console.print("[bold]Running consistency check...[/bold]\n")

        generated_text = "\n\n".join([f"## {k}\n{v}" for k, v in generated_sections.items()])

        check_prompt = f"""Review this newly generated content for "{note_name}" against the established lore.

GENERATED CONTENT:
{generated_text[:3000]}

ESTABLISHED LORE CONTEXT:
{chr(10).join(related_context[:5])}

Check for:
1. **Name inconsistencies** - Are names spelled correctly? Do titles match?
2. **Timeline conflicts** - Do dates/eras align with established history?
3. **Relationship errors** - Are faction relationships accurate?
4. **Factual contradictions** - Does anything conflict with established facts?

If there are issues, list them specifically. If the content is consistent, say "No issues found."
Be concise."""

        with Status("[dim]Checking consistency...[/dim]", console=console, spinner="dots"):
            check_response = chat_with_context(
                check_prompt,
                sources=all_sources[:10],
                provider=DEFAULT_PROVIDER
            )

        if "no issues" in check_response.lower():
            console.print("[green]Consistency check passed[/green]\n")
        else:
            console.print(Panel(
                Markdown(check_response),
                title="[yellow]Consistency Notes[/yellow]",
                border_style="yellow"
            ))

    # Show preview
    for section, sect_content in generated_sections.items():
        console.print(Panel(
            Markdown(sect_content[:600] + ("..." if len(sect_content) > 600 else "")),
            title=f"[bold]{section}[/bold]",
            border_style="blue"
        ))

    if not save:
        console.print("\n[dim]Use --save to write to file[/dim]")
        return

    # Rebuild the note
    new_content = frontmatter_raw + "\n" if frontmatter_raw else ""

    intro = current_sections.get("_intro", "")
    if intro:
        new_content += intro.rstrip() + "\n\n"

    # Merge sections
    all_sections = {}
    all_sections.update(current_sections)
    for k, v in generated_sections.items():
        if k not in filled:
            all_sections[k] = v

    # Order by template
    section_order = []
    if template_headings:
        section_order = template_headings.copy()
    for s in all_sections.keys():
        if s != "_intro" and s not in section_order:
            section_order.append(s)

    # Build final content
    for section in section_order:
        if section in all_sections and section != "_intro":
            sect_content = all_sections[section]
            if sect_content.strip():
                new_content += f"## {section}\n{sect_content}\n\n"
            else:
                new_content += f"## {section}\n\n"

    # Backup and save
    backup_path = full_path.with_suffix(".md.bak")
    backup_path.write_text(content, encoding="utf-8")
    console.print(f"[dim]Backup: {backup_path.name}[/dim]")

    full_path.write_text(new_content.rstrip() + "\n", encoding="utf-8")
    console.print(f"[green]Saved: {file_path}[/green]")


@cli.command()
@click.option("--port", "-p", default=5000, help="Port to run on")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
def web(port: int, host: str):
    """Launch the web interface.

    Opens a browser-based chat UI similar to Gemini AI Studio.
    """
    console.print(f"\n[bold blue]Aetherion AI Web Interface[/bold blue]")
    console.print(f"[dim]Starting server at http://{host}:{port}[/dim]\n")

    import webbrowser
    from web import app

    # Open browser after short delay
    import threading
    threading.Timer(1.5, lambda: webbrowser.open(f"http://{host}:{port}")).start()

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    cli()
