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
