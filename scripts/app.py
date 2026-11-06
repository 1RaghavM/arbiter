import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

import psycopg
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


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


def ensure_database(env):
    url = env["DATABASE_URL"]
    params = psycopg.conninfo.conninfo_to_dict(url)
    local = params.get("host") in ("localhost", "127.0.0.1", "::1")
    if local and (ROOT / ".local" / f"postgres-{params.get('port', 5432)}").exists():
        url = psycopg.conninfo.make_conninfo(
            url, host="127.0.0.1", password=params.get("password") or "arbiter"
        )
        env["DATABASE_URL"] = url
    try:
        with psycopg.connect(url, connect_timeout=3):
            return
    except psycopg.Error:
        pass
    params = psycopg.conninfo.conninfo_to_dict(url)
    if params.get("host") not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError(
            "Cannot connect to remote DATABASE_URL. Start that database first."
        )
    port = int(params.get("port", 5432))
    if free_port(port) != port:
        raise RuntimeError(
            "The database port is occupied but DATABASE_URL cannot connect. "
            "Check its credentials and database name."
        )
    user = params.get("user", "arbiter")
    database = params.get("dbname", user)
    password = params.get("password", "")
    password = password or "arbiter"
    url = psycopg.conninfo.make_conninfo(url, host="127.0.0.1", password=password)
    env["DATABASE_URL"] = url
    pg_ctl = shutil.which("pg_ctl")
    if not pg_ctl:
        for prefix in ("/opt/homebrew", "/usr/local"):
            candidate = Path(prefix) / "opt/postgresql@17/bin/pg_ctl"
            if candidate.is_file():
                pg_ctl = str(candidate)
                break
    if pg_ctl:
        binaries = Path(pg_ctl).parent
        data = ROOT / ".local" / f"postgres-{port}"
        data.parent.mkdir(exist_ok=True)
        if not (data / "PG_VERSION").exists():
            with tempfile.NamedTemporaryFile(mode="w") as secret:
                secret.write(password + "\n")
                secret.flush()
                run(
                    [
                        str(binaries / "initdb"),
                        "-D",
                        str(data),
                        "-U",
                        user,
                        "--auth=scram-sha-256",
                        "--pwfile",
                        secret.name,
                    ],
                    ROOT,
                    env,
                )
        run(
            [
                pg_ctl,
                "-D",
                str(data),
                "-l",
                str(data / "server.log"),
                "-o",
                f"-h 127.0.0.1 -p {port}",
                "-w",
                "start",
            ],
            ROOT,
            env,
        )
        admin = psycopg.conninfo.make_conninfo(url, dbname="postgres")
        with psycopg.connect(admin, autocommit=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (database,)
            ).fetchone():
                connection.execute(
                    psycopg.sql.SQL("CREATE DATABASE {}").format(
                        psycopg.sql.Identifier(database)
                    )
                )
    else:
        env.update(
            ARBITER_DB_PORT=str(port),
            ARBITER_DB_USER=user,
            ARBITER_DB_PASSWORD=password,
            ARBITER_DB_NAME=database,
        )
        run(["docker", "compose", "up", "-d", "--wait", "db"], ROOT, env)
    with psycopg.connect(env["DATABASE_URL"], connect_timeout=3):
        pass


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
    ensure_database(env)
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
    except (subprocess.CalledProcessError, OSError, psycopg.Error):
        print(
            "Setup failed. Check the command output and .env; see docs/SETUP.md.",
            file=sys.stderr,
        )
        raise SystemExit(1)
