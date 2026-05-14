from pathlib import Path
import pytest


@pytest.fixture
def tmp_devpost_dir(tmp_path: Path) -> Path:
    """Isolated ~/.devpost replacement for tests."""
    d = tmp_path / ".devpost"
    d.mkdir()
    return d
