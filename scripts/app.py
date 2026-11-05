import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")
DEFAULT_DB = "postgresql://arbiter:arbiter@localhost:5432/arbiter"


def validate(values):
    missing = []
    if not (values.get("JEV_API_KEY") or "").strip():
        missing.append("JEV_API_KEY")
    if not any((values.get(key) or "").strip() for key in PROVIDERS):
        missing.append("at least one of " + ", ".join(PROVIDERS))
    if not (values.get("DATABASE_URL") or "").strip():
        missing.append("DATABASE_URL")
    if missing:
        raise RuntimeError("Edit .env and fill in: " + "; ".join(missing))


def free_port(preferred):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", preferred))
        except OSError:
            sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(args, cwd, env):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def wait_ready(url, children):
    for _ in range(120):
        if any(child.poll() is not None for child in children):
            raise RuntimeError("A server exited during startup; see output above.")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Startup timed out: " + url)


def main():
    values = dotenv_values(ROOT / ".env", interpolate=False)
    validate(values)
    env = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    env["CHAT_MODE"] = "live"
    # Keep provider credentials out of frontend build and server processes.
    frontend_env = {
        k: v
        for k, v in os.environ.items()
        if k not in (*PROVIDERS, "JEV_API_KEY", "DATABASE_URL")
    }
    backend = ROOT / "backend"
    frontend = ROOT / "frontend"
    try:
        with psycopg.connect(env["DATABASE_URL"], connect_timeout=3):
            pass
    except psycopg.Error:
        if env["DATABASE_URL"] != DEFAULT_DB:
            raise RuntimeError(
                "Cannot connect to DATABASE_URL. Start that database first."
            ) from None
        port = free_port(5432)
        env["ARBITER_DB_PORT"] = str(port)
        run(["docker", "compose", "up", "-d", "--wait", "db"], ROOT, env)
        env["DATABASE_URL"] = DEFAULT_DB.replace("localhost:5432", f"127.0.0.1:{port}")
    run([sys.executable, "-m", "app.db"], backend, env)
    run(["npm", "ci"], frontend, frontend_env)
    run(["npm", "run", "build"], frontend, frontend_env)
    api_port = free_port(8000)
    web_port = free_port(5173)
    frontend_env["ARBITER_API_URL"] = f"http://127.0.0.1:{api_port}"
    children = []
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    try:
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
                cwd=backend,
                env=env,
            )
        )
        wait_ready(f"http://127.0.0.1:{api_port}/api/runs?limit=1", children)
        children.append(
            subprocess.Popen(
                [
                    "npm",
                    "run",
                    "preview",
                    "--",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
                cwd=frontend,
                env=frontend_env,
                start_new_session=True,
            )
        )
        url = f"http://127.0.0.1:{web_port}"
        wait_ready(url + "/api/runs?limit=1", children)
        print(
            f"\nArbiter is ready: {url}\n"
            "Ctrl+C stops the app. PostgreSQL data is retained.",
            flush=True,
        )
        while all(child.poll() is None for child in children):
            time.sleep(1)
        raise RuntimeError("A server stopped; see output above.")
    finally:
        for index, child in reversed(list(enumerate(children))):
            if child.poll() is None:
                if index == 1:
                    os.killpg(child.pid, signal.SIGTERM)
                else:
                    child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if index == 1:
                        os.killpg(child.pid, signal.SIGKILL)
                    else:
                        child.kill()
                    child.wait()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    except (subprocess.CalledProcessError, OSError):
        print(
            "Setup failed. Check the command output and .env; see docs/SETUP.md.",
            file=sys.stderr,
        )
        raise SystemExit(1)
