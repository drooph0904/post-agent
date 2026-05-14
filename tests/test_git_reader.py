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
    assert "Total commits: 3" in summary
    assert "third commit" in summary


def test_since_hash_not_found_falls_back_to_24h(repo):
    repo_path, _ = repo
    reader = GitReader(str(repo_path))
    # Pass a garbage hash that doesn't exist in history; fallback returns last 24h commits
    result = reader.get_commits_since_hash("deadbeef000000")
    assert len(result) > 0
