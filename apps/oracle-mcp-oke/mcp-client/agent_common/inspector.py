import os
import shutil
import signal
import socket
import subprocess
import threading
import time

from .config import resolve_public_inspector_ui_url


_inspector_process: subprocess.Popen | None = None
_inspector_lock = threading.Lock()


def _pids_listening_on_port(port: int) -> list[int]:
    try:
        proc = subprocess.run(
            ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        return [int(line.strip()) for line in (proc.stdout or "").splitlines() if line.strip().isdigit()]
    except Exception:
        return []


def _terminate_pids(pids: list[int]) -> list[int]:
    killed: list[int] = []
    for pid in sorted(set(int(p) for p in pids if int(p) > 0)):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except Exception:
            continue
    if killed:
        time.sleep(0.6)
        for pid in list(killed):
            try:
                os.kill(pid, signal.SIGKILL)
            except Exception:
                pass
    return killed


def launch_inspector(client_port: int = 6274, server_port: int = 6277) -> str:
    global _inspector_process
    npx_cmd = shutil.which("npx")
    if not npx_cmd:
        return "**Error:** `npx` not found on PATH. Install Node.js >= 22."

    def _port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    if _port_in_use(client_port) or _port_in_use(server_port):
        port_pids = [str(pid) for pid in (_pids_listening_on_port(client_port) + _pids_listening_on_port(server_port))]
        return (
            f"**Error:** Port conflict. `{client_port}` or `{server_port}` is already in use. "
            f"Listener PID(s): {', '.join(port_pids) if port_pids else 'unknown'}. "
            "Use Stop Inspector to force-clean stale listeners or choose different ports."
        )

    with _inspector_lock:
        if _inspector_process is not None and _inspector_process.poll() is None:
            _inspector_process.terminate()
            try:
                _inspector_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _inspector_process.kill()

        env = {**os.environ, "CLIENT_PORT": str(client_port), "SERVER_PORT": str(server_port)}
        try:
            _inspector_process = subprocess.Popen(
                [npx_cmd, "-y", "@modelcontextprotocol/inspector"],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            return f"**Error launching Inspector:** {exc}"

    time.sleep(1.0)
    if _inspector_process is None:
        return "**Error:** Inspector process did not start."
    if _inspector_process.poll() is not None:
        stderr = ""
        stdout = ""
        if _inspector_process.stderr is not None:
            try:
                stderr = _inspector_process.stderr.read() or ""
            except Exception:
                stderr = ""
        if _inspector_process.stdout is not None:
            try:
                stdout = _inspector_process.stdout.read() or ""
            except Exception:
                stdout = ""
        _inspector_process = None
        return f"**Error launching Inspector:** {(stderr or stdout or 'Inspector exited during startup.').strip()}"

    url = resolve_public_inspector_ui_url(client_port)
    return (
        f"**Inspector launched** (PID {_inspector_process.pid})\n\n"
        f"Open: [{url}]({url})\n\n"
        "Select `streamable-http` transport and paste your MCP server URL."
    )


def stop_inspector() -> str:
    global _inspector_process
    forced_killed: list[int] = []
    with _inspector_lock:
        if _inspector_process is None or _inspector_process.poll() is not None:
            _inspector_process = None
            pids = _pids_listening_on_port(6274) + _pids_listening_on_port(6277)
            forced_killed = _terminate_pids(pids)
            if forced_killed:
                return f"Inspector tracker was empty; force-stopped listener PID(s): {', '.join(str(pid) for pid in forced_killed)}."
            return "Inspector is not running."
        pid = _inspector_process.pid
        _inspector_process.terminate()
        try:
            _inspector_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _inspector_process.kill()
        _inspector_process = None
    pids = _pids_listening_on_port(6274) + _pids_listening_on_port(6277)
    forced_killed = _terminate_pids(pids)
    if forced_killed:
        return f"Inspector (PID {pid}) stopped. Also force-stopped listener PID(s): {', '.join(str(item) for item in forced_killed)}."
    return f"Inspector (PID {pid}) stopped."


def inspector_status() -> str:
    with _inspector_lock:
        if _inspector_process is not None and _inspector_process.poll() is None:
            return f"**Running** (PID {_inspector_process.pid})"
    return "**Stopped**"