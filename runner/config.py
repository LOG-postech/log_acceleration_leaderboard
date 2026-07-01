"""Shared config + paths for the leaderboard runner.

Single source of truth is ``docs/data/config.json`` — the same file the
static site reads — so the runner and the site never drift apart.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "docs" / "data" / "config.json"
RESULTS_JSON = REPO_ROOT / "docs" / "data" / "results.json"
RAW_RESULTS_DIR = REPO_ROOT / "results"

CATEGORIES = ("short", "medium", "long")


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def normalize_gpu(name: str) -> str:
    """Map an nvidia-smi device name to a leaderboard baseline key."""
    n = (name or "").upper()
    if "A100" in n:
        return "A100"
    if "A6000" in n or "RTX A6000" in n:
        return "A6000"
    if "PRO 6000" in n or "PRO6000" in n or "RTX PRO 6000" in n:
        return "PRO6000"
    if "3090" in n:
        return "RTX3090"
    if "A10G" in n or "A10" in n:
        return "A10G"
    if "H100" in n:
        return "H100"
    return name or "unknown"


def detect_gpu() -> str:
    """Best-effort detection of the GPU this eval is running on."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=15,
        )
        first = out.strip().splitlines()[0].strip()
        return normalize_gpu(first)
    except Exception:
        return os.environ.get("LB_GPU", "unknown")


def default_model(cfg: dict) -> str:
    """Primary model id — used as the baselines/results key when a
    submission manifest omits an explicit ``model``."""
    return cfg.get("model") or (cfg.get("models") or ["unknown"])[0]


def baseline_for(cfg: dict, gpu: str, model: str) -> dict | None:
    """Return {short, medium, long} baseline medians for a (model, GPU), or None.

    Speedup is only meaningful within a fixed (model, GPU) pair — different
    GPUs and different models have different absolute latencies — so baselines
    are nested ``baselines[model][gpu]``.
    """
    b = ((cfg.get("baselines") or {}).get(model) or {}).get(gpu)
    if not b:
        return None
    if all(b.get(c) for c in CATEGORIES):
        return {c: b[c] for c in CATEGORIES}
    return None
