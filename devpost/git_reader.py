# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data flow through this file:
#
# MODE A (has post log):
#   repo_path + last_commit_hash
#     → get_commits_since_hash(hash)
#     → walk git log, stop when we hit the saved hash
#     → return only new commits as list[dict]
#
# MODE B (first run / --force flag):
#   repo_path + hours
#     → get_commits_last_hours(hours)
#     → filter by authored_datetime >= now - hours
#     → return commits as list[dict]
#
# Both modes return the same dict structure so agent.py
# doesn't need to know which mode was used.
#
# After both modes: summarize_changes() formats the result
# into a plain-English string that gets sent to Claude.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import git
from rich.console import Console

_console = Console()


class GitReader:
    def __init__(self, repo_path: str = ".") -> None:
        try:
            self.repo = git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            raise ValueError(f"{repo_path} is not a git repository")
        self.repo_path = str(Path(repo_path).resolve())

    def _format_commit(self, commit) -> dict:
        return {
            "hash": commit.hexsha[:7],
            "full_hash": commit.hexsha,
            "message": commit.message.strip(),
            "author": commit.author.name,
            "timestamp": commit.authored_datetime.isoformat(),
            "files_changed": list(commit.stats.files.keys()),
            "insertions": commit.stats.total["insertions"],
            "deletions": commit.stats.total["deletions"],
        }

    def get_commits_since_hash(self, last_hash: str) -> list[dict]:
        results: list[dict] = []
        for commit in self.repo.iter_commits():
            if commit.hexsha == last_hash or commit.hexsha.startswith(last_hash):
                return results
            results.append(self._format_commit(commit))
        # Hash not found — likely a rebase changed history
        if results:
            _console.print(
                f"[yellow]⚠️  Saved hash {last_hash[:7]} not in history "
                f"(rebase?). Falling back to last 24h.[/yellow]"
            )
            return self.get_commits_last_hours(24)
        return results

    def get_commits_last_hours(self, hours: int = 24) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        results: list[dict] = []
        for commit in self.repo.iter_commits():
            commit_dt = commit.authored_datetime.astimezone(timezone.utc)
            if commit_dt >= cutoff:
                results.append(self._format_commit(commit))
            else:
                break
        return results

    def get_newest_hash(self, commits: list[dict]) -> Optional[str]:
        if not commits:
            return None
        return commits[0]["full_hash"]

    def summarize_changes(self, commits: list[dict]) -> str:
        if not commits:
            return ""
        all_files: set[str] = set()
        total_ins = 0
        total_del = 0
        for c in commits:
            all_files.update(c["files_changed"])
            total_ins += c["insertions"]
            total_del += c["deletions"]
        lines = [
            f"Total commits: {len(commits)}",
            "",
            "Commits (newest first):",
        ]
        for c in commits:
            lines.append(f'  - {c["hash"]}: "{c["message"]}"')
        lines.append("")
        lines.append(f"Files touched: {', '.join(sorted(all_files))}")
        lines.append(f"Total changes: +{total_ins} lines added, -{total_del} lines removed")
        return "\n".join(lines)
