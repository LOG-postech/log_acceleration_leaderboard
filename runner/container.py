"""Docker container lifecycle helpers for evaluating a submission.

A submission is an EQC-style Docker image exposing, on port 8080:
  GET  /ping                 health (200 when the model can serve)
  POST /v1/completions       latency benchmark (raw prompt)
  POST /v1/chat/completions  quality benchmark (chat template)
  POST /invocations          generic
"""
from __future__ import annotations

import subprocess
import time
import urllib.request
import urllib.error


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True, **kw)


def load_image(image_tar: str) -> None:
    """`docker load` an image.tar.gz. Raises on failure."""
    print(f"[docker] loading image {image_tar} ...", flush=True)
    r = _run(["docker", "load", "-i", image_tar])
    if r.returncode != 0:
        raise RuntimeError(f"docker load failed: {r.stderr.strip()}")
    print(f"[docker] {r.stdout.strip()}", flush=True)


def start(image: str, name: str, host_port: int, gpus: str = "all",
          container_port: int = 8080, extra_args: list[str] | None = None) -> None:
    """Start the submission container detached."""
    rm(name)  # clean any stale container with the same name
    cmd = [
        "docker", "run", "-d", "--rm",
        "--gpus", gpus,
        "-p", f"{host_port}:{container_port}",
        "--name", name,
    ]
    cmd += (extra_args or [])
    cmd += [image]
    print(f"[docker] {' '.join(cmd)}", flush=True)
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"docker run failed: {r.stderr.strip()}")


def wait_healthy(base_url: str, timeout_s: int = 900, health_path: str = "/ping") -> None:
    """Poll GET {base_url}{health_path} until it returns 200."""
    url = f"{base_url}{health_path}"
    print(f"[docker] waiting for {url} (timeout {timeout_s}s) ...", flush=True)
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    print(f"[docker] healthy after {time.perf_counter() - t0:.0f}s", flush=True)
                    return
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        elapsed = int(time.perf_counter() - t0)
        if elapsed and elapsed % 30 == 0:
            print(f"[docker]  [{elapsed}s] still loading ...", flush=True)
        time.sleep(3)
    raise RuntimeError(f"container not healthy after {timeout_s}s")


def logs(name: str, tail: int = 40) -> str:
    r = _run(["docker", "logs", "--tail", str(tail), name])
    return (r.stdout or "") + (r.stderr or "")


def rm(name: str) -> None:
    """Stop + remove a container by name (no error if it does not exist)."""
    _run(["docker", "rm", "-f", name])
