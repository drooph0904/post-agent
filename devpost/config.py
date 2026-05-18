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
        required = ["openai_api_key"]
        missing = [f"missing: {k}" for k in required if not self.get(k)]
        return (len(missing) == 0, missing)

    def has_reddit_credentials(self) -> bool:
        keys = ["reddit_client_id", "reddit_client_secret", "reddit_username", "reddit_password"]
        return all(self.get(k) for k in keys)

    def setup_wizard(self) -> None:
        _console.print(Panel(
            "[bold cyan]DevPost Agent Setup[/bold cyan]\n"
            "Enter your API credentials. They'll be saved to ~/.devpost/config.json.",
            title="🚀 Welcome",
        ))
        fields = {
            "openai_api_key": "OpenAI API key",
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
