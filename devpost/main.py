from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from devpost.config import ConfigManager
from devpost.post_log import PostLog

console = Console()

CONTEXT_TEMPLATE = """\
# Project Context for DevPost Agent

## Project Name
[Your project name]

## What It Does
[1-2 sentences describing what your project does and who it's for]

## Tech Stack
[List your main technologies — e.g. Python, FastAPI, React, PostgreSQL]

## Current Stage
[e.g. "Early MVP", "Side project", "Learning project", "Week 2 of building"]

## Your Goal With This Project
[e.g. "Learning backend development", "Building my first SaaS", "Portfolio project"]

## Tone Preference
[e.g. "Casual and honest", "Technical and precise", "Beginner sharing journey"]

## Twitter Handle (optional)
[@yourhandle]
"""


@click.group()
def cli() -> None:
    """DevPost — daily Git progress to Reddit + clipboard tweet."""


@cli.command()
@click.option("--path", default=".", help="Path to git repo (default: current directory)")
@click.option(
    "--force",
    type=int,
    default=None,
    is_flag=False,
    flag_value=24,
    help="Ignore post log; optionally specify hours to look back (e.g. --force 72, default: 24)",
)
@click.option("--dry-run", is_flag=True, help="Preview everything, change nothing")
def run(path: str, force: int | None, dry_run: bool) -> None:
    """Read new commits and generate Reddit posts + tweet."""
    from devpost.agent import DevPostAgent

    config = ConfigManager()

    if not dry_run:
        valid, missing = config.validate()
        if not valid:
            console.print("[red]Missing credentials:[/red]")
            for m in missing:
                console.print(f"  [red]{m}[/red]")
            console.print("\nRun [bold]devpost setup[/bold] to configure.")
            raise click.Abort()

    agent = DevPostAgent(config=config)
    agent.run(project_path=path, force_hours=force, dry_run=dry_run)


@cli.command()
def setup() -> None:
    """Configure API credentials interactively."""
    ConfigManager().setup_wizard()


@cli.command()
def init() -> None:
    """Create project_context.md template in current directory."""
    ctx_file = Path("project_context.md")
    if ctx_file.exists():
        console.print("[yellow]project_context.md already exists.[/yellow]")
        return
    ctx_file.write_text(CONTEXT_TEMPLATE)
    console.print("[green]✓ Created project_context.md — fill it in to improve post quality.[/green]")


@cli.command()
def status() -> None:
    """Show tracked projects and their last posted commit hash."""
    entries = PostLog().get_all_entries()
    if not entries:
        console.print("[yellow]No projects tracked yet. Run 'devpost run' first.[/yellow]")
        return
    table = Table(title="📌 DevPost Tracked Projects", show_header=True, header_style="bold cyan")
    table.add_column("Repo Path", style="cyan")
    table.add_column("Last Posted Commit", style="green")
    for path, commit_hash in entries.items():
        table.add_row(path, commit_hash[:7])
    console.print(table)


@cli.command()
def reset() -> None:
    """Clear the post log for the current directory."""
    current_dir = str(Path(".").resolve())
    log = PostLog()
    if log.get_last_hash(current_dir) is None:
        console.print("[yellow]No post log entry for current directory.[/yellow]")
        return
    if click.confirm(
        f"Clear post log for {current_dir}? Next run will fetch the last 24 hours of commits.",
        default=False,
    ):
        log.clear_log(current_dir)
        console.print("[green]✓ Post log cleared for current directory.[/green]")
