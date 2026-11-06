import importlib.util
import socket
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "launcher", Path(__file__).resolve().parents[2] / "scripts/app.py"
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


@pytest.mark.parametrize("provider", launcher.PROVIDERS)
def test_one_provider_is_enough(provider):
    launcher.validate({"JEV_API_KEY": "test", provider: "test", "DATABASE_URL": "test"})


@pytest.mark.parametrize(
    "values",
    [{}, {"JEV_API_KEY": "test"}, {"OPENAI_API_KEY": "test", "DATABASE_URL": "test"}],
)
def test_missing_configuration(values):
    with pytest.raises(RuntimeError, match="Edit .env"):
        launcher.validate(values)


def test_busy_port_is_not_reused():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        assert launcher.free_port(port) != port


def test_remote_database_is_never_provisioned(monkeypatch):
    def unavailable(*args, **kwargs):
        raise launcher.psycopg.OperationalError()

    monkeypatch.setattr(launcher.psycopg, "connect", unavailable)
    with pytest.raises(RuntimeError, match="remote DATABASE_URL"):
        launcher.ensure_database({"DATABASE_URL": "postgresql://user@remote/db"})


def test_busy_database_port_is_not_replaced(monkeypatch):
    def unavailable(*args, **kwargs):
        raise launcher.psycopg.OperationalError()

    monkeypatch.setattr(launcher.psycopg, "connect", unavailable)
    monkeypatch.setattr(launcher, "free_port", lambda port: port + 1)
    with pytest.raises(RuntimeError, match="port is occupied"):
        launcher.ensure_database({"DATABASE_URL": "postgresql://user@localhost/db"})
