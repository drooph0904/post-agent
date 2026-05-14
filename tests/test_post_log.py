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
