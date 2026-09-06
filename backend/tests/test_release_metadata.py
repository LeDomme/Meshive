import json
import tomllib
from pathlib import Path

from meshive import __version__


def test_release_versions_are_consistent() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    backend_project = tomllib.loads(
        (repository_root / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    )
    frontend_package = json.loads(
        (repository_root / "frontend" / "package.json").read_text(encoding="utf-8")
    )
    frontend_lock = json.loads(
        (repository_root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )

    assert __version__ == "1.6.0"
    assert backend_project["project"]["version"] == __version__
    assert frontend_package["version"] == __version__
    assert frontend_lock["version"] == __version__
    assert frontend_lock["packages"][""]["version"] == __version__
