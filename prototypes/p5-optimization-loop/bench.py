#!/usr/bin/env python3
"""Benchmark for the P5 optimization loop.

Starts the CMS server (live mode), publishes an article, then hammers
GET /articles/:id from concurrent threads. Prints JSON: requests/sec and
latency percentiles. This file is FROZEN for the optimizing agent.
"""
import json
import os
import pathlib
import signal
import statistics
import subprocess
import sys
import threading
import time

import requests

HERE = pathlib.Path(__file__).resolve().parent
SERVER_DIR = HERE / ".." / ".." / "examples" / "cms" / "app" / "server"
ADDR = "127.0.0.1:3400"
BASE = f"http://{ADDR}"
THREADS = 16
DURATION = 5.0


def start_server() -> subprocess.Popen:
    env = dict(os.environ, AUTH_MODE="live", CMS_ADDR=ADDR)
    p = subprocess.Popen(
        ["cargo", "run", "--quiet"], cwd=SERVER_DIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid)
    for _ in range(120):
        try:
            requests.get(f"{BASE}/health", timeout=0.5)
            return p
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("server did not come up")


def setup_published_article() -> int:
    alice = requests.post(f"{BASE}/login", json={"user": "alice"}).json()["token"]
    eve = requests.post(f"{BASE}/login", json={"user": "eve"}).json()["token"]
    art = requests.post(f"{BASE}/articles",
                        headers={"authorization": f"Bearer {alice}"},
                        json={"title": "bench", "body": "x" * 2048}).json()
    aid = art["id"]
    requests.post(f"{BASE}/articles/{aid}/submit",
                  headers={"authorization": f"Bearer {alice}"})
    requests.post(f"{BASE}/articles/{aid}/publish",
                  headers={"authorization": f"Bearer {eve}"})
    return aid


def worker(aid: int, stop: float, lat: list, errs: list) -> None:
    s = requests.Session()
    while time.perf_counter() < stop:
        t0 = time.perf_counter()
        try:
            r = s.get(f"{BASE}/articles/{aid}", timeout=5)
            if r.status_code != 200:
                errs.append(r.status_code)
        except Exception:
            errs.append("exc")
            continue
        lat.append(time.perf_counter() - t0)


def main() -> None:
    proc = start_server()
    try:
        aid = setup_published_article()
        # warmup
        for _ in range(50):
            requests.get(f"{BASE}/articles/{aid}")
        lat: list = []
        errs: list = []
        stop = time.perf_counter() + DURATION
        threads = [threading.Thread(target=worker, args=(aid, stop, lat, errs))
                   for _ in range(THREADS)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t0
        lat.sort()
        result = {
            "requests": len(lat),
            "errors": len(errs),
            "rps": round(len(lat) / wall, 1),
            "p50_ms": round(1000 * lat[len(lat) // 2], 2) if lat else None,
            "p95_ms": round(1000 * lat[int(len(lat) * 0.95)], 2) if lat else None,
        }
        print(json.dumps(result))
        if errs:
            sys.exit(2)
    finally:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)


if __name__ == "__main__":
    main()
