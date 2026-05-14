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
    # Inject a stale key before the second run to verify it gets wiped
    agent.results["stale_key"] = "stale_value"
    run_with_mocks(agent, mock_log, mock_tweet, mock_reddit, tmp_path, commits=commits)
    assert "stale_key" not in agent.results
    assert "tweet" in agent.results

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
