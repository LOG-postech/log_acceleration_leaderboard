"""Latency benchmark against a running submission container.

Mirrors the AdaptFM EQC methodology (see eqc/model_eval/efficiency/):
  - three categories: short (64/128), medium (2048/256), long (8192/256)
  - N warmup runs + M measured runs per category, report the median
  - measure HTTP round-trip latency to POST /v1/completions (raw prompt)
  - speedup = per-GPU dense baseline / measured median

Absolute numbers depend on the GPU, so speedup is only comparable within
the same GPU. Baselines live in docs/data/config.json.
"""
from __future__ import annotations

import json
import statistics
import time
import urllib.request
import urllib.error
from typing import Any

FILLER = "The quick brown fox jumps over the lazy dog. "


def _post(base_url: str, path: str, body: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        f"{base_url}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_model_id(base_url: str) -> str:
    """Ask the OpenAI-compatible server which model id it serves."""
    try:
        with urllib.request.urlopen(f"{base_url}/v1/models", timeout=15) as resp:
            data = json.loads(resp.read())
        return data["data"][0]["id"]
    except Exception:
        return "default"


def _invoke(base_url: str, model: str, prompt: str, max_tokens: int) -> float:
    t0 = time.perf_counter()
    _post(base_url, "/v1/completions", {
        "model": model,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.0,
    })
    return (time.perf_counter() - t0) * 1000.0


def run_latency(base_url: str, cfg: dict, baseline: dict | None,
                model: str | None = None) -> dict[str, Any]:
    """Run the full 3-category latency sweep. Returns a latency dict:

        {"short": {"median_ms", "speedup", "num_runs"}, ..., "avg_speedup"}
    """
    lat_cfg = cfg["latency"]
    warmup = int(lat_cfg.get("warmup_runs", 5))
    measure = int(lat_cfg.get("measure_runs", 50))
    categories = lat_cfg["categories"]
    model = model or get_model_id(base_url)
    print(f"[latency] model id: {model}", flush=True)

    out: dict[str, Any] = {}
    speedups: list[float] = []
    for cat in ("short", "medium", "long"):
        c = categories[cat]
        prompt = FILLER * max(1, c["prompt_tokens"] // 10)
        max_new = c["output_tokens"]
        for _ in range(warmup):
            try:
                _invoke(base_url, model, prompt, max_new)
            except Exception:
                pass
        print(f"[latency] [{cat}] warmup done, measuring {measure} runs ...", flush=True)

        lat: list[float] = []
        for i in range(measure):
            try:
                lat.append(_invoke(base_url, model, prompt, max_new))
            except Exception as e:
                print(f"[latency] [{cat}] run {i+1} FAILED: {e}", flush=True)
            if (i + 1) % 10 == 0:
                print(f"[latency] [{cat}] {i+1}/{measure}", flush=True)

        if not lat:
            out[cat] = {"median_ms": None, "speedup": None, "num_runs": 0}
            continue
        median = round(statistics.median(lat), 2)
        speedup = None
        if baseline and baseline.get(cat):
            speedup = round(baseline[cat] / median, 3)
            speedups.append(speedup)
        out[cat] = {"median_ms": median, "speedup": speedup, "num_runs": len(lat)}
        bl = baseline.get(cat) if baseline else None
        print(f"[latency] [{cat}] median {median}ms"
              + (f"  baseline {bl}ms  speedup {speedup}x" if speedup else "  (no baseline)"), flush=True)

    out["avg_speedup"] = round(statistics.mean(speedups), 3) if speedups else None
    return out
