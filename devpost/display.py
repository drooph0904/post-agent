from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

console = Console()


def print_header() -> None:
    console.print(Panel(
        "[bold cyan]🚀 DevPost Agent v0.1.0[/bold cyan]\n"
        "[dim]Daily progress → Reddit + Clipboard[/dim]",
        border_style="cyan",
    ))


def print_step(step_number: int, total: int, message: str) -> None:
    console.print(f"\n[cyan][{step_number}/{total}] {message}[/cyan]")


def print_thinking(message: str) -> None:
    console.print(f"  [dim italic]🤖 {message}[/dim italic]")


def print_post_log_status(has_hash: bool, hash_val: Optional[str], repo_name: str) -> None:
    if has_hash and hash_val:
        console.print(
            f"  [blue]📌 Post log found — fetching commits since "
            f"[bold]{hash_val[:7]}[/bold] in {repo_name}[/blue]"
        )
    else:
        console.print(
            f"  [blue]🆕 First run for [bold]{repo_name}[/bold] "
            f"— fetching last 24 hours of commits[/blue]"
        )


def print_git_summary(summary: str) -> None:
    console.print(Panel(summary, title="[bold]📂 Git Activity[/bold]", border_style="blue"))


def print_no_new_commits(repo_name: str, last_hash: str) -> None:
    console.print(Panel(
        f"  No new commits in [bold]{repo_name}[/bold] since last post "
        f"(commit [bold]{last_hash[:7]}[/bold]).\n"
        f"  Nothing to post about yet — write some code first! 💪\n\n"
        f"  [dim]Tip: Use --force to post about the last 24h regardless.[/dim]",
        border_style="yellow",
    ))


def print_tweet_draft(tweet: str, char_count: int) -> None:
    count_color = "green" if char_count <= 280 else "red"
    console.print(Panel(
        f"{tweet}\n\n"
        f"[{count_color}]{char_count}/280 characters[/{count_color}]\n"
        f"[dim]✓ Will be copied to clipboard on approval[/dim]",
        title="[bold]🐦 Tweet Draft[/bold]",
        border_style="blue",
    ))


def print_reddit_draft(subreddit: str, title: str, body: str, index: int, total: int) -> None:
    preview = body[:300] + "..." if len(body) > 300 else body
    console.print(Panel(
        f"[bold]{title}[/bold]\n\n{preview}\n\n[dim]Full post: {len(body)} characters[/dim]",
        title=f"[bold]📋 Reddit [{index}/{total}] — r/{subreddit}[/bold]",
        border_style="magenta",
    ))


def ask_tweet_approval(tweet: str, char_count: int) -> bool:
    print_tweet_draft(tweet, char_count)
    return Confirm.ask("  Copy this tweet to clipboard?", default=False)


def ask_reddit_approval(subreddit: str, title: str, body: str, index: int, total: int) -> bool:
    print_reddit_draft(subreddit, title, body, index, total)
    return Confirm.ask(f"  Post to r/{subreddit}?", default=False)


def print_post_log_saved(commit_hash: str) -> None:
    console.print(
        f"  [green]💾 Post log updated — next run starts from commit "
        f"[bold]{commit_hash[:7]}[/bold][/green]"
    )
    console.print("  [dim]Next run will only show commits newer than this.[/dim]")


def print_success(message: str) -> None:
    console.print(f"  [green]✅ {message}[/green]")


def print_error(message: str) -> None:
    console.print(f"  [red]❌ {message}[/red]")


def print_warning(message: str) -> None:
    console.print(f"  [yellow]⚠️  {message}[/yellow]")


def print_final_summary(results: dict) -> None:
    table = Table(title="📊 Run Summary", show_header=True, header_style="bold")
    table.add_column("Action", style="cyan")
    table.add_column("Result")
    for action, result in results.items():
        if str(result).startswith("posted") or result == "copied":
            style, icon = "green", "✅"
        elif result == "skipped" or str(result).startswith("dry-run"):
            style, icon = "yellow", "⏭"
        else:
            style, icon = "red", "❌"
        table.add_row(action, f"[{style}]{icon} {result}[/{style}]")
    console.print(table)
