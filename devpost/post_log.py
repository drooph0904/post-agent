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
