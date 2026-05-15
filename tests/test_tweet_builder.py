from unittest.mock import MagicMock, patch
import pytest
from devpost.tweet_builder import TweetBuilder


@pytest.fixture
def builder():
    return TweetBuilder(client=MagicMock())


def _make_response(text: str) -> MagicMock:
    r = MagicMock()
    r.choices = [MagicMock(message=MagicMock(content=text))]
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
    builder.client.chat.completions.create.return_value = _make_response(short_tweet)
    tweet, count = builder.generate("summary", "context")
    assert tweet == short_tweet
    assert count == len(short_tweet)
    assert count <= 280
    assert builder.client.chat.completions.create.call_count == 1


def test_generate_retries_when_tweet_too_long(builder):
    long_tweet = "x" * 300
    short_tweet = "Short. #buildinpublic"
    builder.client.chat.completions.create.side_effect = [
        _make_response(long_tweet),
        _make_response(short_tweet),
    ]
    tweet, count = builder.generate("summary", "context")
    assert tweet == short_tweet
    assert builder.client.chat.completions.create.call_count == 2


def test_copy_to_clipboard_returns_true_on_success(builder):
    with patch("devpost.tweet_builder.pyperclip") as mock_clip:
        assert builder.copy_to_clipboard("test tweet") is True
        mock_clip.copy.assert_called_once_with("test tweet")


def test_copy_to_clipboard_returns_false_on_error(builder):
    with patch("devpost.tweet_builder.pyperclip") as mock_clip:
        mock_clip.copy.side_effect = Exception("clipboard unavailable")
        assert builder.copy_to_clipboard("test tweet") is False
