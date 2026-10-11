import pytest

from app import config


@pytest.fixture(autouse=True)
def isolated_env_file(monkeypatch, tmp_path):
    # Tests must never load developer credentials or the live database from .env.
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / ".env")
