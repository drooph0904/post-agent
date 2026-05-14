# DevPost Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Pre-commit requirement:** Before every `git commit`, print the pre-commit summary block (see design spec). Never batch commits. One logical unit = one commit.
>
> **Anthropic SDK note:** When implementing tweet_builder.py, reddit_poster.py, or agent.py, invoke the `claude-api` skill — those files import `anthropic` and the skill ensures correct SDK usage.

**Goal:** Build a CLI agent that reads only new Git commits since the last post, generates a tweet (≤280 chars, clipboard) and 6 subreddit-specific Reddit posts, shows everything for approval, posts approved content, and tracks what was posted to prevent redundancy.

**Architecture:** 8 focused modules coordinated by a stateful orchestrator (agent.py). The post log (post_log.py) provides persistent memory between runs keyed by absolute repo path. All terminal output flows through a single display module. GitReader has two modes: hash-based (returning user) and time-based (first run / --force).

**Tech Stack:** Python 3.11+, Anthropic SDK ≥0.40.0 (`claude-sonnet-4-6`), Click 8.1.7, Rich 13.7.1, PRAW 7.7.1, GitPython 3.1.43, Pyperclip 1.8.2, pytest ≥7.0, pytest-mock ≥3.10

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package config, pinned deps, entry point |
| `.gitignore` / `.env.example` | Repo hygiene, credential template |
| `devpost/__init__.py` | Empty package marker |
| `devpost/config.py` | ConfigManager — credential storage and setup wizard |
| `devpost/post_log.py` | PostLog — per-repo hash tracking between runs |
| `devpost/git_reader.py` | GitReader — dual-mode commit fetching |
| `devpost/display.py` | All Rich terminal output (no print() elsewhere) |
| `devpost/tweet_builder.py` | TweetBuilder — self-correction loop, clipboard |
| `devpost/reddit_poster.py` | RedditPoster — 6 persona prompts + PRAW posting |
| `devpost/agent.py` | DevPostAgent — central orchestrator |
| `devpost/main.py` | Click CLI — 5 commands |
| `README.md` | Setup guide and agent pattern docs |
| `project_context.example.md` | Template for per-project context |
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/test_config.py` | ConfigManager unit tests |
| `tests/test_post_log.py` | PostLog unit tests |
| `tests/test_git_reader.py` | GitReader unit tests (uses temp git repo) |
| `tests/test_tweet_builder.py` | TweetBuilder unit tests (mocked Claude) |
| `tests/test_reddit_poster.py` | RedditPoster unit tests (mocked PRAW + Claude) |
| `tests/test_agent.py` | DevPostAgent integration tests (all deps mocked) |
| `tests/test_main.py` | CLI tests with Click CliRunner |

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `devpost/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p devpost tests
touch devpost/__init__.py tests/__init__.py
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.DS_Store
dist/
*.egg-info/
build/
.venv/
venv/
*.log
.pytest_cache/
```

- [ ] **Step 3: Create `.env.example`**

```
ANTHROPIC_API_KEY=your_anthropic_key_here
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
REDDIT_USER_AGENT=devpost-agent/0.1 by /u/your_reddit_username
```

- [ ] **Step 4: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "devpost-agent"
version = "0.1.0"
description = "Daily Git progress to Reddit and clipboard tweet — student developer agent"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "rich==13.7.1",
    "click==8.1.7",
    "python-dotenv==1.0.1",
    "praw==7.7.1",
    "gitpython==3.1.43",
    "pyperclip==1.8.2",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-mock>=3.10",
]

[project.scripts]
devpost = "devpost.main:cli"

[tool.setuptools.packages.find]
where = ["."]
include = ["devpost*"]
```

- [ ] **Step 5: Create `tests/conftest.py`**

```python
from pathlib import Path
import pytest


@pytest.fixture
def tmp_devpost_dir(tmp_path: Path) -> Path:
    """Isolated ~/.devpost replacement for tests."""
    d = tmp_path / ".devpost"
    d.mkdir()
    return d
```

- [ ] **Step 6: Install dependencies**

```bash
pip install anthropic rich click python-dotenv praw gitpython pyperclip
pip install pytest pytest-mock
pip install -e .
```

Expected: All packages install without errors.

- [ ] **Step 7: Verify package registration**

```bash
devpost --help
```

Expected: Error like `No such command` or import error — confirms the entry point is registered even though commands aren't implemented yet.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore .env.example devpost/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: initialize devpost project, dependencies, and package structure"
```

---

### Task 2: ConfigManager

**Files:**
- Create: `devpost/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import json
import os
from pathlib import Path
import pytest
from devpost.config import ConfigManager


@pytest.fixture
def config(tmp_devpost_dir):
    return ConfigManager(config_dir=tmp_devpost_dir)


def test_validate_all_missing(config):
    valid, missing = config.validate()
    assert not valid
    assert len(missing) == 5


def test_validate_all_present_via_env(config, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ak-test")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
    monkeypatch.setenv("REDDIT_USERNAME", "user")
    monkeypatch.setenv("REDDIT_PASSWORD", "pass")
    valid, missing = config.validate()
    assert valid
    assert missing == []


def test_env_var_takes_priority_over_file(config, monkeypatch):
    config.set("anthropic_api_key", "from_file")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from_env")
    assert config.get("anthropic_api_key") == "from_env"


def test_get_fallback_when_missing(config):
    assert config.get("nonexistent_key", "default") == "default"


def test_set_persists_to_disk(tmp_devpost_dir):
    mgr = ConfigManager(config_dir=tmp_devpost_dir)
    mgr.set("test_key", "test_value")
    config_file = tmp_devpost_dir / "config.json"
    data = json.loads(config_file.read_text())
    assert data["test_key"] == "test_value"


def test_load_bad_json_returns_empty(tmp_devpost_dir):
    (tmp_devpost_dir / "config.json").write_text("not json {{{")
    mgr = ConfigManager(config_dir=tmp_devpost_dir)
    assert mgr.config == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.config'`

- [ ] **Step 3: Write `devpost/config.py`**

```python
import json
import os
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

_console = Console()


class ConfigManager:
    DEFAULT_DIR = Path.home() / ".devpost"

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        self._dir = config_dir if config_dir is not None else self.DEFAULT_DIR
        self._file = self._dir / "config.json"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.config = self._load()

    def _load(self) -> dict:
        if not self._file.exists():
            return {}
        try:
            return json.loads(self._file.read_text())
        except json.JSONDecodeError:
            _console.print("[yellow]⚠️  Config file corrupted — starting fresh.[/yellow]")
            return {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self.config, indent=2))

    def get(self, key: str, fallback: Optional[str] = None) -> Optional[str]:
        env_val = os.environ.get(key.upper())
        if env_val:
            return env_val
        return self.config.get(key, fallback)

    def set(self, key: str, value: str) -> None:
        self.config[key] = value
        self._save()

    def validate(self) -> tuple[bool, list[str]]:
        required = [
            "anthropic_api_key",
            "reddit_client_id",
            "reddit_client_secret",
            "reddit_username",
            "reddit_password",
        ]
        missing = [f"missing: {k}" for k in required if not self.get(k)]
        return (len(missing) == 0, missing)

    def setup_wizard(self) -> None:
        _console.print(Panel(
            "[bold cyan]DevPost Agent Setup[/bold cyan]\n"
            "Enter your API credentials. They'll be saved to ~/.devpost/config.json.",
            title="🚀 Welcome",
        ))
        fields = {
            "anthropic_api_key": "Anthropic API key",
            "reddit_client_id": "Reddit client ID",
            "reddit_client_secret": "Reddit client secret",
            "reddit_username": "Reddit username",
            "reddit_password": "Reddit password",
        }
        values: dict[str, str] = {}
        for key, label in fields.items():
            values[key] = Prompt.ask(
                f"  {label}",
                password=("password" in key or "secret" in key),
            )

        if Confirm.ask("Save to ~/.devpost/config.json?", default=False):
            for k, v in values.items():
                self.set(k, v)
            _console.print("[green]✓ Config saved. You won't need to do this again.[/green]")
        else:
            _console.print(
                "[yellow]Credentials not saved. Set them as environment variables instead.[/yellow]"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/config.py tests/test_config.py
git commit -m "feat: config manager with first-run setup wizard and credential validation"
```

---

### Task 3: PostLog

**Files:**
- Create: `devpost/post_log.py`
- Create: `tests/test_post_log.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_post_log.py`:

```python
from pathlib import Path
import os
import pytest
from devpost.post_log import PostLog


@pytest.fixture
def log(tmp_devpost_dir):
    return PostLog(log_dir=tmp_devpost_dir)


def test_unknown_repo_returns_none(log, tmp_path):
    assert log.get_last_hash(str(tmp_path / "myrepo")) is None


def test_save_and_retrieve_hash(log, tmp_path):
    repo = str(tmp_path / "myrepo")
    log.save_last_hash(repo, "abc123def456full")
    assert log.get_last_hash(repo) == "abc123def456full"


def test_path_normalized_to_absolute(log, tmp_path):
    repo_abs = str(tmp_path / "myrepo")
    log.save_last_hash(repo_abs, "aaa111")
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        assert log.get_last_hash("myrepo") == "aaa111"
    finally:
        os.chdir(old_cwd)


def test_clear_removes_entry(log, tmp_path):
    repo = str(tmp_path / "myrepo")
    log.save_last_hash(repo, "abc123")
    log.clear_log(repo)
    assert log.get_last_hash(repo) is None


def test_size_limit_trims_oldest(tmp_devpost_dir, tmp_path):
    log = PostLog(log_dir=tmp_devpost_dir)
    for i in range(55):
        log.save_last_hash(str(tmp_path / f"repo{i}"), f"hash{i:040d}")
    assert len(log.log) <= 45


def test_get_all_entries_returns_copy(log, tmp_path):
    log.save_last_hash(str(tmp_path / "a"), "hash_a")
    log.save_last_hash(str(tmp_path / "b"), "hash_b")
    entries = log.get_all_entries()
    assert len(entries) == 2
    entries["injected"] = "should_not_affect_log"
    assert len(log.log) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_post_log.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.post_log'`

- [ ] **Step 3: Write `devpost/post_log.py`**

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Persistent State Between Runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Most agents are stateless — they start fresh every run.
# But some agents need memory between runs to avoid doing
# the same work twice. This is that memory.
#
# The problem this solves:
# If you run devpost run at 10am (3 commits) and again at
# 2pm (2 new commits), without a log the second run would
# include all 5 commits again — duplicating your 10am post.
# With the log, the 2pm run only sees the 2 new commits.
#
# How it works:
# After any successful post (tweet copied OR any reddit posted),
# we save the hash of the newest commit that was included.
# Next run: git_reader fetches ONLY commits newer than that hash.
# If no new commits exist: agent exits with "nothing new to post."
#
# Data flow:
# devpost run → PostLog.get_last_hash(repo_path)
#   → if hash exists: GitReader.get_commits_since_hash(hash)
#   → if no hash: GitReader.get_commits_last_hours(24) [first run]
# After posting: PostLog.save_last_hash(repo_path, newest_commit_hash)
#
# The log is keyed by absolute repo path so multiple projects
# each have their own independent tracking.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import json
from pathlib import Path
from typing import Optional

_MAX_ENTRIES = 50
_TRIM_TO = 40


class PostLog:
    DEFAULT_DIR = Path.home() / ".devpost"

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._dir = log_dir if log_dir is not None else self.DEFAULT_DIR
        self._file = self._dir / "post_log.json"
        self._dir.mkdir(parents=True, exist_ok=True)
        self.log = self._load()

    def _load(self) -> dict:
        if not self._file.exists():
            return {}
        try:
            return json.loads(self._file.read_text())
        except json.JSONDecodeError:
            return {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self.log, indent=2))

    def _normalize(self, repo_path: str) -> str:
        return str(Path(repo_path).resolve())

    def get_last_hash(self, repo_path: str) -> Optional[str]:
        return self.log.get(self._normalize(repo_path))

    def save_last_hash(self, repo_path: str, commit_hash: str) -> None:
        self.log[self._normalize(repo_path)] = commit_hash
        if len(self.log) > _MAX_ENTRIES:
            keys = list(self.log.keys())
            for old_key in keys[: len(keys) - _TRIM_TO]:
                del self.log[old_key]
        self._save()

    def clear_log(self, repo_path: str) -> None:
        self.log.pop(self._normalize(repo_path), None)
        self._save()

    def get_all_entries(self) -> dict[str, str]:
        return dict(self.log)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_post_log.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/post_log.py tests/test_post_log.py
git commit -m "feat: post log — persistent commit tracking to prevent redundant posts"
```

---

### Task 4: GitReader

**Files:**
- Create: `devpost/git_reader.py`
- Create: `tests/test_git_reader.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_git_reader.py`:

```python
import subprocess
from pathlib import Path
import pytest
from devpost.git_reader import GitReader


@pytest.fixture
def repo(tmp_path):
    """Minimal git repo with 3 commits: oldest→newest order in hashes[0..2]."""
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path)] + list(args),
                       check=True, capture_output=True)

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    git("config", "user.email", "test@test.com")
    git("config", "user.name", "Test")

    hashes = []
    for i, msg in enumerate(["first commit", "second commit", "third commit"]):
        f = tmp_path / f"file{i}.txt"
        f.write_text(f"content {i}")
        git("add", f.name)
        git("commit", "-m", msg)
        result = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        )
        hashes.append(result.stdout.strip())

    return tmp_path, hashes  # hashes[0]=first/oldest, hashes[2]=third/newest


def test_invalid_repo_raises(tmp_path):
    with pytest.raises(ValueError, match="not a git repository"):
        GitReader(str(tmp_path))


def test_get_commits_last_hours_returns_all_recent(repo):
    repo_path, _ = repo
    reader = GitReader(str(repo_path))
    commits = reader.get_commits_last_hours(24)
    assert len(commits) == 3


def test_get_commits_since_hash_excludes_base_commit(repo):
    repo_path, hashes = repo
    reader = GitReader(str(repo_path))
    newer = reader.get_commits_since_hash(hashes[0])
    messages = [c["message"] for c in newer]
    assert len(newer) == 2
    assert "second commit" in messages
    assert "third commit" in messages
    assert "first commit" not in messages


def test_get_commits_since_newest_returns_empty(repo):
    repo_path, hashes = repo
    reader = GitReader(str(repo_path))
    assert reader.get_commits_since_hash(hashes[2]) == []


def test_get_newest_hash_matches_latest_commit(repo):
    repo_path, hashes = repo
    reader = GitReader(str(repo_path))
    commits = reader.get_commits_last_hours(24)
    assert reader.get_newest_hash(commits) == hashes[2]


def test_get_newest_hash_empty_list_returns_none(repo):
    repo_path, _ = repo
    reader = GitReader(str(repo_path))
    assert reader.get_newest_hash([]) is None


def test_summarize_changes_empty_returns_empty_string(repo):
    repo_path, _ = repo
    reader = GitReader(str(repo_path))
    assert reader.summarize_changes([]) == ""


def test_summarize_changes_includes_count_and_messages(repo):
    repo_path, _ = repo
    reader = GitReader(str(repo_path))
    commits = reader.get_commits_last_hours(24)
    summary = reader.summarize_changes(commits)
    assert "New commits since last post: 3" in summary
    assert "third commit" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_git_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.git_reader'`

- [ ] **Step 3: Write `devpost/git_reader.py`**

```python
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

    def get_repo_stats(self) -> dict:
        all_commits = list(self.repo.iter_commits())
        return {
            "repo_name": Path(self.repo_path).name,
            "current_branch": self.repo.active_branch.name,
            "total_commits": len(all_commits),
            "last_commit_message": all_commits[0].message.strip() if all_commits else "",
        }

    def summarize_changes(self, commits: list[dict]) -> str:
        if not commits:
            return ""
        stats = self.get_repo_stats()
        all_files: set[str] = set()
        total_ins = 0
        total_del = 0
        for c in commits:
            all_files.update(c["files_changed"])
            total_ins += c["insertions"]
            total_del += c["deletions"]
        lines = [
            f"Repository: {stats['repo_name']} (branch: {stats['current_branch']})",
            f"New commits since last post: {len(commits)}",
            "",
            "Commits (newest first):",
        ]
        for c in commits:
            lines.append(f'  - {c["hash"]}: "{c["message"]}"')
        lines.append("")
        lines.append(f"Files touched: {', '.join(sorted(all_files))}")
        lines.append(f"Total changes: +{total_ins} lines added, -{total_del} lines removed")
        return "\n".join(lines)

    def validate_repo(self) -> bool:
        try:
            next(self.repo.iter_commits())
            return True
        except StopIteration:
            _console.print("[yellow]⚠️  Repository has no commits yet.[/yellow]")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_git_reader.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/git_reader.py tests/test_git_reader.py
git commit -m "feat: git reader — dual-mode commit fetching (hash-based and time-based)"
```

---

### Task 5: Display Module

**Files:**
- Create: `devpost/display.py`

(No unit tests — Rich output is verified visually and exercised through integration tests in later tasks.)

- [ ] **Step 1: Write `devpost/display.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add devpost/display.py
git commit -m "feat: display module — all Rich terminal UI including post log status messages"
```

---

### Task 6: TweetBuilder

> ⚠️ **Invoke the `claude-api` skill before implementing this task** — this file imports `anthropic`.

**Files:**
- Create: `devpost/tweet_builder.py`
- Create: `tests/test_tweet_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tweet_builder.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from devpost.tweet_builder import TweetBuilder


@pytest.fixture
def builder():
    return TweetBuilder(client=MagicMock())


def _make_response(text: str) -> MagicMock:
    r = MagicMock()
    r.content = [MagicMock(text=text)]
    return r


def test_count_chars(builder):
    assert builder._count_chars("hello") == 5
    assert builder._count_chars("a" * 280) == 280
    assert builder._count_chars("") == 0


def test_build_prompt_first_attempt_contains_git_and_context(builder):
    prompt = builder._build_prompt("git summary here", "my project context")
    assert "280 characters" in prompt
    assert "git summary here" in prompt
    assert "my project context" in prompt
    assert "previous" not in prompt.lower()


def test_build_prompt_retry_contains_overage_and_previous(builder):
    prompt = builder._build_prompt("s", "c", previous_attempt="old tweet text", chars_over=15)
    assert "15 characters too long" in prompt
    assert "old tweet text" in prompt


def test_generate_valid_tweet_returned_immediately(builder):
    short_tweet = "Built something cool today! #buildinpublic"
    builder.client.messages.create.return_value = _make_response(short_tweet)
    tweet, count = builder.generate("summary", "context")
    assert tweet == short_tweet
    assert count == len(short_tweet)
    assert count <= 280
    assert builder.client.messages.create.call_count == 1


def test_generate_retries_when_tweet_too_long(builder):
    long_tweet = "x" * 300
    short_tweet = "Short. #buildinpublic"
    builder.client.messages.create.side_effect = [
        _make_response(long_tweet),
        _make_response(short_tweet),
    ]
    tweet, count = builder.generate("summary", "context")
    assert tweet == short_tweet
    assert builder.client.messages.create.call_count == 2


def test_copy_to_clipboard_returns_true_on_success(builder):
    with patch("devpost.tweet_builder.pyperclip") as mock_clip:
        assert builder.copy_to_clipboard("test tweet") is True
        mock_clip.copy.assert_called_once_with("test tweet")


def test_copy_to_clipboard_returns_false_on_error(builder):
    with patch("devpost.tweet_builder.pyperclip") as mock_clip:
        mock_clip.copy.side_effect = Exception("clipboard unavailable")
        assert builder.copy_to_clipboard("test tweet") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tweet_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.tweet_builder'`

- [ ] **Step 3: Write `devpost/tweet_builder.py`**

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Self-Correction Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Claude generates a tweet → code checks character count →
# if over 280: sends draft BACK to Claude with the error
# and exact overage → Claude retries → repeat until valid.
#
# The user never sees an over-limit tweet. The loop is
# invisible to them — they only see the final valid draft.
#
# Data flow:
# git_summary + project_context
#   → Claude (attempt 1) → tweet draft
#   → count chars → if >280: chars_over = count - 280
#   → Claude (attempt 2) with previous draft + chars_over
#   → repeat up to 5 times
#   → valid tweet returned to agent.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from typing import Optional

import anthropic
import pyperclip

from devpost import display


class TweetBuilder:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self.client = client
        self.max_retries = 5
        self.model = "claude-sonnet-4-6"

    def _count_chars(self, text: str) -> int:
        return len(text)

    def _build_prompt(
        self,
        git_summary: str,
        context: str,
        previous_attempt: Optional[str] = None,
        chars_over: Optional[int] = None,
    ) -> str:
        if previous_attempt is not None and chars_over is not None:
            return (
                f"Your previous tweet was {chars_over} characters too long "
                f"({len(previous_attempt)} total).\n\n"
                f"Previous attempt:\n{previous_attempt}\n\n"
                f"Rewrite it to be STRICTLY under 280 characters.\n"
                f"Strategies: shorten phrases, cut one hashtag, simplify wording.\n"
                f"Keep the core message. Return ONLY the new tweet text."
            )
        return (
            "You are writing a tweet for a student developer sharing daily coding progress.\n\n"
            "Tone: honest, learning in public, curious, not corporate or hype-y.\n"
            "Show real progress and real struggles — not marketing language.\n\n"
            f"Project context:\n{context}\n\n"
            f"What was built/changed (from Git):\n{git_summary}\n\n"
            "Write ONE tweet that:\n"
            "- Is STRICTLY under 280 characters (count every character)\n"
            "- Shares what was actually built or learned\n"
            "- Feels genuine, like a real student developer talking\n"
            "- Ends with 2-3 relevant hashtags from: #buildinpublic #learntocode "
            "#100daysofcode #webdev #coding #AI #ML #sideproject\n"
            "- Does NOT use em dashes, ellipsis, or overly formal language\n\n"
            "Return ONLY the tweet text. Nothing else."
        )

    def generate(self, git_summary: str, context: str) -> tuple[str, int]:
        previous_attempt: Optional[str] = None
        chars_over: Optional[int] = None

        for attempt in range(1, self.max_retries + 1):
            display.print_thinking(f"Generating tweet (attempt {attempt}/{self.max_retries})...")
            prompt = self._build_prompt(git_summary, context, previous_attempt, chars_over)
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30.0,
                )
                tweet = response.content[0].text.strip()
            except Exception as e:
                display.print_warning(f"Claude API error on attempt {attempt}: {e}")
                continue

            count = self._count_chars(tweet)
            if count <= 280:
                display.print_thinking(f"Tweet valid: {count}/280 chars")
                return tweet, count

            chars_over = count - 280
            display.print_thinking(f"Tweet too long: {count} chars ({chars_over} over). Retrying...")
            previous_attempt = tweet

        # Fallback: truncate at word boundary
        fallback = git_summary[:270].rsplit(" ", 1)[0] + "..."
        return fallback[:280], len(fallback[:280])

    def copy_to_clipboard(self, tweet: str) -> bool:
        try:
            pyperclip.copy(tweet)
            return True
        except Exception as e:
            display.print_warning(f"Clipboard copy failed: {e}\n\nTweet:\n{tweet}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tweet_builder.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/tweet_builder.py tests/test_tweet_builder.py
git commit -m "feat: tweet builder with self-correction loop — core agent pattern"
```

---

### Task 7: RedditPoster

> ⚠️ **Invoke the `claude-api` skill before implementing this task** — this file imports `anthropic`.

**Files:**
- Create: `devpost/reddit_poster.py`
- Create: `tests/test_reddit_poster.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reddit_poster.py`:

```python
import json
from unittest.mock import MagicMock, patch
import pytest
from devpost.reddit_poster import RedditPoster, SUBREDDIT_PERSONAS


def make_poster():
    client = MagicMock()
    config = MagicMock()
    config.get.side_effect = lambda key, fallback=None: {
        "reddit_client_id": "test_id",
        "reddit_client_secret": "test_secret",
        "reddit_username": "test_user",
        "reddit_password": "test_pass",
        "reddit_user_agent": "test_agent",
    }.get(key, fallback)
    with patch("devpost.reddit_poster.praw.Reddit"):
        poster = RedditPoster(client=client, config=config)
    return poster, client


def test_subreddit_personas_has_six_keys():
    expected = {"SideProject", "webdev", "learnprogramming", "coding", "artificial", "MachineLearning"}
    assert set(SUBREDDIT_PERSONAS.keys()) == expected


def test_generate_post_parses_json_response():
    poster, client = make_poster()
    post_data = {"title": "Test title", "body": "Test body here"}
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(post_data))]
    client.messages.create.return_value = mock_response
    result = poster._generate_post("SideProject", "git summary", "context")
    assert result["title"] == "Test title"
    assert result["body"] == "Test body here"


def test_generate_all_returns_all_six_subreddits():
    poster, client = make_poster()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({"title": "T", "body": "B"}))]
    client.messages.create.return_value = mock_response
    results = poster.generate_all("summary", "context")
    assert len(results) == 6
    assert set(results.keys()) == set(SUBREDDIT_PERSONAS.keys())


def test_post_to_subreddit_returns_url_on_success():
    poster, _ = make_poster()
    mock_sub = MagicMock()
    mock_sub.url = "https://reddit.com/r/SideProject/comments/abc"
    poster.reddit.subreddit.return_value.submit.return_value = mock_sub
    url = poster.post_to_subreddit("SideProject", "Title", "Body")
    assert url == "https://reddit.com/r/SideProject/comments/abc"


def test_post_to_subreddit_returns_none_on_failure():
    poster, _ = make_poster()
    poster.reddit.subreddit.return_value.submit.side_effect = Exception("API error")
    assert poster.post_to_subreddit("SideProject", "Title", "Body") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_reddit_poster.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.reddit_poster'`

- [ ] **Step 3: Write `devpost/reddit_poster.py`**

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Context-Aware Multi-Output Generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Same Git commits → 6 different Reddit posts.
# Each uses a subreddit-specific persona prompt that tells
# Claude the community's culture and expectations.
#
# Data flow:
# git_summary + project_context → for each subreddit:
#   persona prompt → Claude → {title, body} JSON
#   → display for approval → PRAW post → URL returned
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import json
from typing import Optional

import anthropic
import praw

from devpost import display
from devpost.config import ConfigManager

SUBREDDIT_PERSONAS: dict[str, dict[str, str]] = {
    "SideProject": {
        "audience": "makers and indie developers who love seeing what others are building",
        "tone": "excited but genuine, share what you built and why",
        "focus": "the product, the idea, the progress milestone",
        "title_style": "I built [X] today — here's what I learned",
        "depth": "medium — 150-250 words",
    },
    "webdev": {
        "audience": "web developers interested in technical implementation",
        "tone": "technical but approachable, share the stack and decisions",
        "focus": "technical choices, what worked, what didn't",
        "title_style": "Built [feature] with [tech] — ran into [problem], here's how I solved it",
        "depth": "technical — 200-300 words with some code context",
    },
    "learnprogramming": {
        "audience": "students and beginners learning to code",
        "tone": "honest about struggles, encouraging, share what you learned not just what you built",
        "focus": "the learning journey, mistakes made, concepts understood",
        "title_style": "Day [X] of learning — finally understood [concept]",
        "depth": "personal — 150-200 words, mention specific things you struggled with",
    },
    "coding": {
        "audience": "general programmers who enjoy seeing coding projects",
        "tone": "casual and friendly, like talking to a fellow dev",
        "focus": "what you coded, interesting problems, progress update",
        "title_style": "Working on [project] — made good progress on [feature] today",
        "depth": "casual — 100-200 words",
    },
    "artificial": {
        "audience": "AI enthusiasts interested in projects using AI/ML",
        "tone": "technically curious, focus on the AI aspect if any",
        "focus": "any AI/ML components, APIs used, interesting behaviors observed",
        "title_style": "Using [AI tool/API] to build [thing] — interesting results",
        "depth": "technical and curious — 200-250 words",
    },
    "MachineLearning": {
        "audience": "ML researchers and practitioners, more technical crowd",
        "tone": "precise and technical, respect the audience's expertise",
        "focus": "technical architecture, model choices, data handling, results",
        "title_style": "[Technical description of what you built or experimented with]",
        "depth": "detailed technical — 250-350 words, use proper ML terminology",
    },
}


class RedditPoster:
    def __init__(self, client: anthropic.Anthropic, config: ConfigManager) -> None:
        self.client = client
        self.model = "claude-sonnet-4-6"
        try:
            self.reddit = praw.Reddit(
                client_id=config.get("reddit_client_id"),
                client_secret=config.get("reddit_client_secret"),
                username=config.get("reddit_username"),
                password=config.get("reddit_password"),
                user_agent=config.get("reddit_user_agent", "devpost-agent/0.1"),
            )
        except Exception as e:
            display.print_error(f"Reddit initialization failed: {e}")
            raise

    def validate_credentials(self) -> bool:
        try:
            self.reddit.user.me()
            return True
        except Exception:
            return False

    def _generate_post(self, subreddit: str, git_summary: str, context: str) -> dict:
        persona = SUBREDDIT_PERSONAS[subreddit]
        prompt = (
            f"Write a Reddit post for r/{subreddit}.\n\n"
            f"Audience: {persona['audience']}\n"
            f"Tone: {persona['tone']}\n"
            f"Focus: {persona['focus']}\n"
            f"Title style: {persona['title_style']}\n"
            f"Depth: {persona['depth']}\n\n"
            f"Project context:\n{context}\n\n"
            f"Git activity:\n{git_summary}\n\n"
            f"Author is a student developer learning in public. Be genuine, not corporate.\n\n"
            f'Return ONLY a JSON object: {{"title": "...", "body": "..."}}\n'
            f"No markdown fences, no explanation — raw JSON only."
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return {"title": data["title"], "body": data["body"]}

    def generate_all(self, git_summary: str, context: str) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for subreddit in SUBREDDIT_PERSONAS:
            display.print_thinking(f"Generating post for r/{subreddit}...")
            try:
                results[subreddit] = self._generate_post(subreddit, git_summary, context)
            except Exception as e:
                display.print_error(f"Failed to generate post for r/{subreddit}: {e}")
                results[subreddit] = {"title": "[generation failed]", "body": ""}
        return results

    def post_to_subreddit(self, subreddit: str, title: str, body: str) -> Optional[str]:
        try:
            submission = self.reddit.subreddit(subreddit).submit(title=title, selftext=body)
            return submission.url
        except Exception as e:
            display.print_error(f"Failed to post to r/{subreddit}: {e}")
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_reddit_poster.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/reddit_poster.py tests/test_reddit_poster.py
git commit -m "feat: reddit poster — subreddit-specific post generation and PRAW posting"
```

---

### Task 8: DevPostAgent

> ⚠️ **Invoke the `claude-api` skill before implementing this task** — this file imports `anthropic`.

**Files:**
- Create: `devpost/agent.py`
- Create: `tests/test_agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from devpost.agent import DevPostAgent

SUBREDDITS = ["SideProject", "webdev", "learnprogramming", "coding", "artificial", "MachineLearning"]


def make_agent():
    config = MagicMock()
    config.get.return_value = "fake_key"
    with (
        patch("devpost.agent.anthropic.Anthropic"),
        patch("devpost.agent.PostLog") as MockLog,
        patch("devpost.agent.TweetBuilder") as MockTweet,
        patch("devpost.agent.RedditPoster") as MockReddit,
    ):
        mock_log = MagicMock()
        MockLog.return_value = mock_log
        mock_tweet = MagicMock()
        MockTweet.return_value = mock_tweet
        mock_reddit = MagicMock()
        MockReddit.return_value = mock_reddit
        agent = DevPostAgent(config=config)
    return agent, mock_log, mock_tweet, mock_reddit


def run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path,
                   commits=None, last_hash=None, tweet_approval=False, reddit_approval=False):
    mock_git = MagicMock()
    mock_git.get_commits_last_hours.return_value = commits or []
    mock_git.get_commits_since_hash.return_value = commits or []
    mock_git.get_repo_stats.return_value = {"repo_name": "testrepo"}
    mock_git.get_newest_hash.return_value = commits[0]["full_hash"] if commits else None
    mock_git.summarize_changes.return_value = "summary text"
    mock_log.get_last_hash.return_value = last_hash
    mock_tweet.generate.return_value = ("tweet text", 50)
    mock_tweet.copy_to_clipboard.return_value = True
    mock_reddit.generate_all.return_value = {s: {"title": "T", "body": "B"} for s in SUBREDDITS}

    with (
        patch("devpost.agent.GitReader", return_value=mock_git),
        patch("devpost.agent.display") as mock_display,
    ):
        mock_display.ask_tweet_approval.return_value = tweet_approval
        mock_display.ask_reddit_approval.return_value = reddit_approval
        result = agent.run(str(tmp_path))

    return result, mock_log, mock_git


def test_no_commits_returns_no_new_status(tmp_path):
    agent, mock_log, mock_tweet, mock_reddit = make_agent()
    result, _, _ = run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path)
    assert result == {"status": "no_new_commits"}


def test_log_not_saved_when_nothing_approved(tmp_path):
    agent, mock_log, mock_tweet, mock_reddit = make_agent()
    commits = [{"full_hash": "abc123full", "message": "test"}]
    _, log, _ = run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path,
                                commits=commits, tweet_approval=False, reddit_approval=False)
    log.save_last_hash.assert_not_called()


def test_log_saved_when_tweet_copied(tmp_path):
    agent, mock_log, mock_tweet, mock_reddit = make_agent()
    commits = [{"full_hash": "abc123full", "message": "test"}]
    _, log, _ = run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path,
                                commits=commits, tweet_approval=True, reddit_approval=False)
    log.save_last_hash.assert_called_once()


def test_results_reset_between_runs(tmp_path):
    agent, mock_log, mock_tweet, mock_reddit = make_agent()
    commits = [{"full_hash": "abc123full", "message": "test"}]
    run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path, commits=commits)
    run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path, commits=commits)
    assert "tweet" in agent.results
    # No stale results from first run bleeding through

def test_dry_run_does_not_save_log(tmp_path):
    agent, mock_log, mock_tweet, mock_reddit = make_agent()
    commits = [{"full_hash": "abc123full", "message": "test"}]
    mock_git = MagicMock()
    mock_git.get_commits_last_hours.return_value = commits
    mock_git.get_repo_stats.return_value = {"repo_name": "testrepo"}
    mock_git.get_newest_hash.return_value = "abc123full"
    mock_git.summarize_changes.return_value = "summary"
    mock_log.get_last_hash.return_value = None
    mock_reddit.generate_all.return_value = {s: {"title": "T", "body": "B"} for s in SUBREDDITS}

    with (
        patch("devpost.agent.GitReader", return_value=mock_git),
        patch("devpost.agent.display"),
    ):
        agent.run(str(tmp_path), dry_run=True)

    mock_log.save_last_hash.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.agent'`

- [ ] **Step 3: Write `devpost/agent.py`**

```python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Stateful Orchestrator with Memory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# This agent has persistent memory (post_log.py) that changes
# its behaviour across runs. It's not the same each time —
# it remembers what it already posted and adapts.
#
# Patterns demonstrated:
# 1. PERSISTENT STATE: post log consulted before any work
# 2. CONDITIONAL TOOL SELECTION: hash-mode vs time-mode git fetch
# 3. CONTEXT INJECTION: project_context.md grounds generation
# 4. TOOL ORCHESTRATION: coordinates 5 modules as tools
# 5. HUMAN-IN-THE-LOOP: pauses before every external action
# 6. SAFE STATE UPDATE: log only saved if something was posted
#
# Full data flow:
# PostLog.get_last_hash(repo)
#   → if hash: GitReader.get_commits_since_hash(hash)
#   → if none: GitReader.get_commits_last_hours(24)
#   → if empty commits: exit with friendly message
#   → GitReader.summarize_changes(commits)
#   → TweetBuilder.generate(summary, context) [self-correction loop inside]
#   → RedditPoster.generate_all(summary, context)
#   → display each for approval
#   → on approval: post/copy
#   → if anything_posted: PostLog.save_last_hash(repo, newest_hash)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from pathlib import Path
from typing import Optional

import anthropic

from devpost import display
from devpost.config import ConfigManager
from devpost.git_reader import GitReader
from devpost.post_log import PostLog
from devpost.reddit_poster import RedditPoster, SUBREDDIT_PERSONAS
from devpost.tweet_builder import TweetBuilder


class DevPostAgent:
    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.get("anthropic_api_key"))
        self.post_log = PostLog()
        self.tweet_builder = TweetBuilder(client=self.client)
        self.reddit_poster = RedditPoster(client=self.client, config=config)
        self.results: dict = {}
        self.anything_posted: bool = False

    def read_context(self, project_path: str) -> str:
        ctx_file = Path(project_path) / "project_context.md"
        if ctx_file.exists():
            return ctx_file.read_text()
        display.print_warning(
            "No project_context.md found. Run 'devpost init' to create one. "
            "Generation will be less specific without context."
        )
        return ""

    def run(self, project_path: str = ".", force: bool = False, dry_run: bool = False) -> dict:
        self.results = {}
        self.anything_posted = False

        display.print_header()

        # Step 1/7 — Read project context
        display.print_step(1, 7, "Reading project context...")
        context = self.read_context(project_path)

        # Step 2/7 — Check post log and fetch commits
        display.print_step(2, 7, "Checking post log and fetching commits...")
        try:
            git_reader = GitReader(project_path)
        except ValueError as e:
            display.print_error(str(e))
            return {"status": "error", "message": str(e)}

        last_hash = self.post_log.get_last_hash(project_path)

        if force or last_hash is None:
            display.print_post_log_status(False, None, git_reader.get_repo_stats()["repo_name"])
            commits = git_reader.get_commits_last_hours(24)
        else:
            display.print_post_log_status(True, last_hash, git_reader.get_repo_stats()["repo_name"])
            commits = git_reader.get_commits_since_hash(last_hash)

        if not commits:
            if last_hash:
                display.print_no_new_commits(git_reader.get_repo_stats()["repo_name"], last_hash)
            else:
                display.print_warning("No commits found in the last 24 hours. Write some code first!")
            return {"status": "no_new_commits"}

        newest_hash = git_reader.get_newest_hash(commits)
        git_summary = git_reader.summarize_changes(commits)
        display.print_git_summary(git_summary)

        # Step 3/7 — Generate tweet
        display.print_step(3, 7, "Generating tweet...")
        display.print_thinking("Sending Git activity to Claude for tweet generation...")
        if dry_run:
            tweet = f"[DRY RUN] {git_summary[:60]}..."
            char_count = len(tweet)
        else:
            tweet, char_count = self.tweet_builder.generate(git_summary, context)

        # Step 4/7 — Generate Reddit posts
        display.print_step(4, 7, "Generating Reddit posts for 6 subreddits...")
        display.print_thinking("Writing unique posts for each community...")
        if dry_run:
            reddit_posts = {s: {"title": f"[DRY RUN] r/{s}", "body": "[DRY RUN]"} for s in SUBREDDIT_PERSONAS}
        else:
            reddit_posts = self.reddit_poster.generate_all(git_summary, context)

        # Step 5/7 — Tweet approval
        display.print_step(5, 7, "Tweet review...")
        if dry_run:
            display.print_tweet_draft(tweet, char_count)
            display.print_thinking("[DRY RUN] Skipping clipboard copy")
            self.results["tweet"] = "dry-run skipped"
        elif display.ask_tweet_approval(tweet, char_count):
            if self.tweet_builder.copy_to_clipboard(tweet):
                display.print_success("Tweet copied to clipboard — paste it on X!")
                self.results["tweet"] = "copied"
                self.anything_posted = True
            else:
                display.print_error("Clipboard copy failed — tweet shown above, copy manually")
                self.results["tweet"] = "failed"
        else:
            display.print_warning("Tweet skipped")
            self.results["tweet"] = "skipped"

        # Step 6/7 — Reddit approval and posting
        display.print_step(6, 7, "Reddit posts review...")
        for i, (subreddit, post) in enumerate(reddit_posts.items(), 1):
            if dry_run:
                display.print_reddit_draft(subreddit, post["title"], post["body"], i, len(reddit_posts))
                display.print_thinking(f"[DRY RUN] Skipping post to r/{subreddit}")
                self.results[f"r/{subreddit}"] = "dry-run skipped"
                continue

            if display.ask_reddit_approval(subreddit, post["title"], post["body"], i, len(reddit_posts)):
                display.print_thinking(f"Posting to r/{subreddit}...")
                url = self.reddit_poster.post_to_subreddit(subreddit, post["title"], post["body"])
                if url:
                    display.print_success(f"Posted → {url}")
                    self.results[f"r/{subreddit}"] = f"posted: {url}"
                    self.anything_posted = True
                else:
                    self.results[f"r/{subreddit}"] = "failed"
            else:
                self.results[f"r/{subreddit}"] = "skipped"

        # Step 7/7 — Save post log
        display.print_step(7, 7, "Wrapping up...")
        if self.anything_posted and newest_hash and not dry_run:
            self.post_log.save_last_hash(project_path, newest_hash)
            display.print_post_log_saved(newest_hash)
        elif dry_run:
            display.print_thinking("[DRY RUN] Post log unchanged.")
        else:
            display.print_thinking(
                "Nothing was posted — post log unchanged. Same commits will appear next run."
            )

        display.print_final_summary(self.results)
        return self.results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_agent.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add devpost/agent.py tests/test_agent.py
git commit -m "feat: agent brain — stateful orchestrator with post log integration"
```

---

### Task 9: CLI Entry Point

**Files:**
- Create: `devpost/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:

```python
from click.testing import CliRunner
from unittest.mock import MagicMock, patch
from devpost.main import cli


def test_help_lists_all_commands():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ["run", "setup", "init", "status", "reset"]:
        assert cmd in result.output


def test_run_help_shows_all_options():
    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--help"])
    assert result.exit_code == 0
    assert "--path" in result.output
    assert "--force" in result.output
    assert "--dry-run" in result.output


def test_init_creates_project_context_file(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(cli, ["init"])
        assert result.exit_code == 0
        import os
        assert os.path.exists("project_context.md")


def test_init_does_not_overwrite_existing_file(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        runner.invoke(cli, ["init"])
        with open("project_context.md", "w") as f:
            f.write("custom content")
        runner.invoke(cli, ["init"])
        with open("project_context.md") as f:
            assert f.read() == "custom content"


def test_status_shows_entries():
    runner = CliRunner()
    with patch("devpost.main.PostLog") as MockLog:
        mock_log = MagicMock()
        mock_log.get_all_entries.return_value = {"/path/to/repo": "abc1234def"}
        MockLog.return_value = mock_log
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "abc1234" in result.output


def test_status_empty_log_shows_message():
    runner = CliRunner()
    with patch("devpost.main.PostLog") as MockLog:
        mock_log = MagicMock()
        mock_log.get_all_entries.return_value = {}
        MockLog.return_value = mock_log
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "No projects tracked" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'devpost.main'`

- [ ] **Step 3: Write `devpost/main.py`**

```python
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
@click.option("--force", is_flag=True, help="Ignore post log, fetch last 24h regardless")
@click.option("--dry-run", is_flag=True, help="Preview everything, change nothing")
def run(path: str, force: bool, dry_run: bool) -> None:
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
    agent.run(project_path=path, force=force, dry_run=dry_run)


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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Verify full CLI**

```bash
devpost --help
```

Expected: Shows all 5 commands with descriptions.

- [ ] **Step 6: Commit**

```bash
git add devpost/main.py tests/test_main.py
git commit -m "feat: CLI — run, setup, init, status, and reset commands"
```

---

### Task 10: Documentation

**Files:**
- Create: `project_context.example.md`
- Create: `README.md`

- [ ] **Step 1: Create `project_context.example.md`**

```markdown
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
```

- [ ] **Step 2: Create `README.md`**

```markdown
# DevPost Agent

> One command. Your new Git commits → Reddit posts + Tweet to clipboard.
> Smart enough to never post about the same commits twice.

## What It Does

DevPost reads only your NEW Git commits since the last post, uses Claude AI
to write platform-specific content for 6 subreddits and a tweet, shows you
everything for approval, then posts to Reddit and copies the tweet to clipboard.

**The smart part:** A post log tracks which commits have been posted. Running
`devpost run` 3 hours after a previous run will only include the 3 hours of new
commits — never redundant content.

## Agent Patterns In This Code

| Pattern | File | What It Teaches |
|---|---|---|
| Self-correction loop | tweet_builder.py | Agent retries until output is valid |
| Persistent state | post_log.py | Agent memory between runs |
| Context injection | agent.py | Grounding agent in real project info |
| Tool orchestration | agent.py | Coordinating multiple tools |
| Human-in-the-loop | agent.py | Approval before external actions |
| Multi-format output | reddit_poster.py | Same data → different audiences |
| Conditional tool selection | agent.py | Hash-mode vs time-mode based on state |

## Setup

### 1. Install

```bash
git clone <your-repo>
cd devpost
pip install -e .
```

### 2. Get Credentials

- **Anthropic API key:** https://console.anthropic.com
- **Reddit API:** reddit.com/prefs/apps → create app → choose "script"

### 3. Configure

```bash
devpost setup
```

### 4. Initialize your project

```bash
cd your-project-folder
devpost init
# fill in project_context.md
```

### 5. Run after a coding session

```bash
devpost run              # only new commits since last post
devpost run --force      # ignore log, use last 24h (for first run or reset)
devpost run --dry-run    # preview everything, change nothing
devpost status           # see what's been tracked across all projects
devpost reset            # clear log for current project
```

## How the Post Log Works

```
First run:
  No log entry → fetch last 24h of commits → post → save newest hash

Second run (2 hours later):
  Log has hash abc1234 → fetch only commits newer than abc1234
  → 2 new commits found → post → update log to newest hash

Third run (30 min later, no new commits):
  Log has hash → fetch since hash → 0 new commits
  → "Nothing new to post — write some code first!" → exit
  → Log unchanged

Run with --force:
  Ignore log → fetch last 24h → show all recent commits
  → useful for reposting or after a rebase
```

## Cost

- Reddit API: **free**
- Anthropic API: ~$0.01–0.03 per run (`claude-sonnet-4-6`, ~1000 tokens)
- Everything else: **free**
```

- [ ] **Step 3: Commit**

```bash
git add README.md project_context.example.md
git commit -m "docs: README with post log explanation, setup guide, and agent patterns"
```

---

### Task 11: Final Verification

**Files:** None new — verification only.

All hardening features are already implemented in earlier tasks:
- **30s timeout**: `tweet_builder.py` Task 6 + `reddit_poster.py` Task 7
- **Post log size limit**: `post_log.py` Task 3 (`_MAX_ENTRIES = 50`, `_TRIM_TO = 40`)
- **Rebase fallback**: `git_reader.py` Task 4 (`get_commits_since_hash` fallback branch)
- **Dry-run mode**: `agent.py` Task 8 + `main.py` Task 9
- **Per-subreddit error isolation**: `reddit_poster.py` Task 7 (`generate_all` try/except per subreddit)
- **Clipboard failure graceful**: `tweet_builder.py` Task 6 (`copy_to_clipboard` try/except)

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS. Zero failures.

- [ ] **Step 2: Verify pyperclip**

```bash
python -c "import pyperclip; pyperclip.copy('devpost test'); print('clipboard OK')"
```

Expected: `clipboard OK`

- [ ] **Step 3: Verify CLI registration**

```bash
devpost --help
```

Expected output includes: `run`, `setup`, `init`, `status`, `reset`

- [ ] **Step 4: Test `devpost init`**

```bash
cd /tmp && mkdir -p devpost_verify && cd devpost_verify && devpost init && cat project_context.md
```

Expected: Prints the template with all 7 sections.

- [ ] **Step 5: Test `devpost status` with empty log**

```bash
devpost status
```

Expected: "No projects tracked yet" message.

- [ ] **Step 6: Test dry-run against this repo**

Run from the devpost project root (it has commits from the build itself):

```bash
devpost run --dry-run
```

Expected: Shows `[DRY RUN]` prefix on all actions. No credential check failure. No log changes. Final summary shows all entries as "dry-run skipped".

- [ ] **Step 7: Final commit and tag**

```bash
git add -A
git commit -m "feat: dry-run mode, hardening, post log size limit, rebase fallback"
git tag -a v0.1.0 -m "DevPost Agent MVP — smart commit tracking, Reddit posting, tweet clipboard"
```

- [ ] **Step 8: Print completion banner**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ DevPost Agent v0.1.0 — Build Complete
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
What you built:
  • 7 agent design patterns in one project
  • Self-correction loop (tweet ≤280 chars)
  • Persistent state (post log — no redundant posts)
  • Context injection (project_context.md)
  • Tool orchestration (git + AI + Reddit + clipboard)
  • Human-in-the-loop (approval before every post)
  • Multi-format output (6 subreddit-specific posts)
  • Conditional tool selection (hash vs time mode)

Commands:
  devpost run           → only new commits, smart post log
  devpost run --force   → ignore log, use last 24h
  devpost run --dry-run → preview everything, change nothing
  devpost status        → see tracked projects and hashes
  devpost reset         → clear log for current project
  devpost setup         → configure credentials
  devpost init          → create project context file

Total commits: 11
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
