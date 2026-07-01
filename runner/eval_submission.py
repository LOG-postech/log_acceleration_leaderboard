#!/usr/bin/env python3
"""Evaluate one submission (an EQC-style Docker image) on the cluster GPU.

    python eval_submission.py submissions/team-quant/submission.yaml

Steps: docker load (if image_tar) -> docker run -> wait /ping -> latency
sweep (-> optional quality) -> stop container -> write raw result ->
rebuild docs/data/results.json.

Baseline calibration (writes measured medians into config.json for the
detected GPU, no submission row produced):

    python eval_submission.py submissions/baseline/dense.yaml --baseline
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C          # noqa: E402
import container            # noqa: E402
import bench_latency        # noqa: E402
import bench_quality        # noqa: E402
import update_results       # noqa: E402


def _sanitize(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", str(s))


def load_manifest(path: str) -> dict:
    with open(path) as f:
        m = yaml.safe_load(f)
    for req in ("team", "submission_id", "image"):
        if not m.get(req):
            sys.exit(f"manifest missing required field: {req}")
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--gpus", default="all", help="docker --gpus value (default: all)")
    ap.add_argument("--host-port", type=int, default=8080)
    ap.add_argument("--quality", action="store_true", help="also run quality gates (else pending)")
    ap.add_argument("--quality-samples", type=int, default=None)
    ap.add_argument("--baseline", action="store_true",
                    help="calibration mode: store measured medians as this GPU's baseline")
    ap.add_argument("--no-update", action="store_true", help="do not rebuild results.json")
    args = ap.parse_args()

    cfg = C.load_config()
    m = load_manifest(args.manifest)
    gpu = C.detect_gpu()
    model = m.get("model") or C.default_model(cfg)
    baseline = C.baseline_for(cfg, gpu, model)
    print(f"[eval] model={model}  GPU={gpu}  "
          f"baseline={'set' if baseline else 'MISSING (speedup will be null)'}", flush=True)

    name = _sanitize(f"lb-{m['team']}-{m['submission_id']}")
    base_url = f"http://127.0.0.1:{args.host_port}"
    container_port = int(m.get("port", cfg["endpoints"]["port"]))
    timeout = int(m.get("startup_timeout_s", 900))

    try:
        if m.get("image_tar"):
            container.load_image(m["image_tar"])
        container.start(
            image=m["image"], name=name, host_port=args.host_port,
            gpus=args.gpus, container_port=container_port,
            extra_args=m.get("docker_args"),
        )
        try:
            container.wait_healthy(base_url, timeout_s=timeout,
                                   health_path=cfg["endpoints"].get("health", "/ping"))
        except Exception:
            print("[eval] container failed to become healthy. Last logs:\n"
                  + container.logs(name), file=sys.stderr)
            raise

        model_id = bench_latency.get_model_id(base_url)

        # In --baseline mode we ignore any stored baseline so speedup is raw.
        latency = bench_latency.run_latency(base_url, cfg,
                                            None if args.baseline else baseline,
                                            model=model_id)
    finally:
        container.rm(name)

    # ---- baseline calibration: store medians into config.json and exit ----
    if args.baseline:
        cfg.setdefault("baselines", {}).setdefault(model, {})[gpu] = {
            c: latency[c]["median_ms"] for c in C.CATEGORIES
        }
        with open(C.CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"[eval] stored baseline for model={model} GPU={gpu} in {C.CONFIG_PATH}: "
              + json.dumps(cfg['baselines'][model][gpu]), flush=True)
        return

    # ---- normal submission result ----
    if args.quality:
        quality = bench_quality.run_quality(base_url, cfg, samples=args.quality_samples, model=model_id)
    else:
        quality = bench_quality.pending_gates(cfg)
    q_status = bench_quality.overall_status(quality)

    result = {
        "team": m["team"],
        "submission_id": m["submission_id"],
        "display_name": m.get("display_name", m["submission_id"]),
        "submitter": m.get("submitter", "—"),
        "model": model,
        "gpu": gpu,
        "image": m["image"],
        "date": date.today().isoformat(),
        "notes": m.get("notes", ""),
        "latency": {c: latency[c] for c in C.CATEGORIES},
        "avg_speedup": latency.get("avg_speedup"),
        "quality": quality,
        "quality_status": q_status,
        "valid": q_status != "fail",
        "status": "ok",
    }

    path = update_results.save_result(result)
    print(f"[eval] wrote {path}", flush=True)
    print(json.dumps(result, indent=2))

    if not args.no_update:
        update_results.write(update_results.rebuild())
        print("[eval] leaderboard rebuilt. Commit docs/data/results.json and push to publish.", flush=True)


if __name__ == "__main__":
    main()
