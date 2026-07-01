"""Quality-gate benchmark against a running submission container.

STATUS: placeholder. Quality gates will be evaluated later with a
*sampled* subset of each benchmark (decided by the team). For now this
module returns every gate as ``pending`` so a submission still appears
on the leaderboard ranked by latency, with quality shown as ⏳.

Contract (from AdaptFM EQC), for when this is filled in:
  Endpoint : POST /v1/chat/completions  (OpenAI chat, port 8080)
  Gates    :
    MMLU-Pro (5-shot)     threshold 0.621 | thinking OFF | max_tok 512
    IFEval   (0-shot)     threshold 0.814 | thinking OFF | max_tok 512
    GPQA-Diamond (0-shot) threshold 0.630 | thinking ON + streaming | max_tok 12288
  Thinking is per-request: body carries
    "chat_template_kwargs": {"enable_thinking": false|true}
  All gates run at concurrency 8. A submission failing ANY gate is invalid.

Implementation sketch (sampling-based) for later:
  - Use lm-eval-harness with the `local-chat-completions` model pointed at
    {base_url}/v1/chat/completions, or a lightweight custom loop that
    samples `--quality-samples` items per task.
  - mmlu_pro / ifeval → enable_thinking=false, max_gen_toks 512
  - gpqa_diamond      → enable_thinking=true,  max_gen_toks 12288, stream
  - Compare each score to its threshold → pass/fail.
"""
from __future__ import annotations

from typing import Any


def pending_gates(cfg: dict) -> dict[str, Any]:
    """Build a quality dict with every gate marked pending."""
    gates = {}
    for key, g in (cfg.get("quality_gates") or {}).items():
        if key == "_comment":
            continue
        gates[key] = {"score": None, "threshold": g.get("threshold"), "status": "pending"}
    return gates


def run_quality(base_url: str, cfg: dict, samples: int | None = None,
                model: str | None = None) -> dict[str, Any]:
    """Return the quality-gate dict.

    Not yet implemented — returns all gates as ``pending``. Wire the
    sampling-based evaluation here (see module docstring) when ready.
    """
    print("[quality] not implemented yet — marking all gates pending "
          "(will be sampled later).", flush=True)
    return pending_gates(cfg)


def overall_status(quality: dict) -> str:
    """Roll gates up into pass / fail / pending."""
    vals = [v for k, v in quality.items() if k != "_comment"]
    if any(v.get("status") == "fail" for v in vals):
        return "fail"
    if vals and all(v.get("status") == "pass" for v in vals):
        return "pass"
    return "pending"
