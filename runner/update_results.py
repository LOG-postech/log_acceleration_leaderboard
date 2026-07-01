"""Merge per-submission eval results into docs/data/results.json.

Reads every raw result JSON in results/ (or a single one passed on the
CLI), then rewrites docs/data/results.json with:
  - submissions : all evaluated runs (flat)
  - groups      : one board per (GPU, model), each independently ranked

Because the dense baseline — and therefore speedup — differs by GPU and by
model, ranking submissions in a single global table would be misleading.
So the leaderboard is split into a board per (GPU, model): within a board,
we keep the best eligible run per team and rank by avg_speedup.

"eligible" = status ok and not quality-failed (pending still counts). A
quality-failed run stays in `submissions` but is dropped from its board.

Usage:
  python update_results.py                 # rebuild from all results/*.json
  python update_results.py path/to.json    # merge one result then rebuild
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

# Board display order; unknown GPUs sort after these, alphabetically.
GPU_ORDER = ["A100", "PRO6000", "3090"]


def _key(r: dict) -> str:
    return f"{r.get('team')}__{r.get('submission_id')}"


def _group_key(r: dict) -> tuple:
    return (r.get("gpu") or "?", r.get("model") or "?")


def _eligible(r: dict) -> bool:
    return r.get("status") == "ok" and r.get("quality_status") != "fail"


def _speed(r: dict) -> float:
    v = r.get("avg_speedup")
    return v if v is not None else -1.0


def rebuild() -> dict:
    raw_files = sorted(glob.glob(str(C.RAW_RESULTS_DIR / "*.json")))
    runs: dict[str, dict] = {}
    for path in raw_files:
        try:
            with open(path) as f:
                r = json.load(f)
        except Exception as e:
            print(f"[update] skipping {path}: {e}", file=sys.stderr)
            continue
        runs[_key(r)] = r  # last write for a team/submission wins

    submissions = sorted(runs.values(), key=_speed, reverse=True)

    # best eligible run per team, bucketed by (gpu, model)
    buckets: dict[tuple, dict[str, dict]] = {}
    for r in submissions:
        if not _eligible(r):
            continue
        gk, team = _group_key(r), r.get("team")
        best = buckets.setdefault(gk, {})
        if team not in best or _speed(r) > _speed(best[team]):
            best[team] = r

    groups = []
    for (gpu, model), teams in buckets.items():
        rows = sorted(teams.values(), key=_speed, reverse=True)
        rows = [{**row, "rank": i} for i, row in enumerate(rows, 1)]
        groups.append({"gpu": gpu, "model": model, "rows": rows})

    def order(g: dict):
        gpu = g["gpu"]
        idx = GPU_ORDER.index(gpu) if gpu in GPU_ORDER else len(GPU_ORDER)
        return (idx, gpu, g["model"])

    groups.sort(key=order)

    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": groups,
        "submissions": submissions,
    }


def save_result(result: dict) -> str:
    """Persist one raw per-submission result under results/."""
    C.RAW_RESULTS_DIR.mkdir(exist_ok=True)
    path = C.RAW_RESULTS_DIR / f"{_key(result)}.json"
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    return str(path)


def write(data: dict) -> None:
    with open(C.RESULTS_JSON, "w") as f:
        json.dump(data, f, indent=2)
    ranked = sum(len(g["rows"]) for g in data["groups"])
    print(f"[update] wrote {C.RESULTS_JSON} "
          f"({ranked} ranked across {len(data['groups'])} board(s) / "
          f"{len(data['submissions'])} total runs)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("result", nargs="?", help="optional single result JSON to merge first")
    args = ap.parse_args()

    if args.result:
        with open(args.result) as f:
            save_result(json.load(f))

    write(rebuild())


if __name__ == "__main__":
    main()
