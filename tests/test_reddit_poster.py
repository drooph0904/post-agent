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
