"""Spawn/kill helper for the cms-server binary, used to give each race
scenario its own clean process (in-memory state means no other reset
mechanism exists).
"""
import os
import subprocess
import time

import requests

SERVER_BIN = os.environ.get(
    "CMS_SERVER_BIN",
    os.path.join(os.path.dirname(__file__), "..", "server", "target", "debug", "cms-server"),
)
PORT = int(os.environ.get("CMS_PORT", "3100"))
BASE_URL = f"http://127.0.0.1:{PORT}"


def start(mode: str, timeout: float = 5.0) -> subprocess.Popen:
    env = dict(os.environ)
    env["AUTH_MODE"] = mode
    env["CMS_ADDR"] = f"0.0.0.0:{PORT}"
    proc = subprocess.Popen(
        [SERVER_BIN],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{BASE_URL}/health", timeout=0.5).status_code == 200:
                return proc
        except requests.RequestException:
            pass
        if proc.poll() is not None:
            raise RuntimeError(f"cms-server ({mode}) exited early with code {proc.returncode}")
        time.sleep(0.1)
    proc.kill()
    raise TimeoutError(f"cms-server ({mode}) did not become healthy in {timeout}s")


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
