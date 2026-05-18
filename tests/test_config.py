import json
import pytest
from devpost.config import ConfigManager


@pytest.fixture
def config(tmp_devpost_dir):
    return ConfigManager(config_dir=tmp_devpost_dir)


def test_validate_all_missing(config):
    valid, missing = config.validate()
    assert not valid
    assert len(missing) == 1
    assert "openai_api_key" in missing[0]


def test_validate_passes_without_reddit_credentials(config, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    valid, missing = config.validate()
    assert valid
    assert missing == []


def test_has_reddit_credentials_false_when_missing(config):
    assert config.has_reddit_credentials() is False


def test_has_reddit_credentials_true_via_env(config, monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csec")
    monkeypatch.setenv("REDDIT_USERNAME", "user")
    monkeypatch.setenv("REDDIT_PASSWORD", "pass")
    assert config.has_reddit_credentials() is True


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
