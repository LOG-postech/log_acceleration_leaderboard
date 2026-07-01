#!/bin/bash
# Evaluate one submission on a cluster GPU via SLURM.
#
#   sbatch --partition=A100 runner/slurm_eval.sh submissions/team-quant/submission.yaml
#
# Partitions on the LOG cluster: A6000, A100, 3090, PRO6000.
# Env knobs:
#   VENV=/path/to/venv        activate this venv first (needs docker CLI + pyyaml)
#   QUALITY=1                 also run quality gates (default: pending)
#   AUTO_PUBLISH=1            git add/commit/push docs/data/results.json when done
#
#SBATCH --job-name=lb-eval
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=slurm-lb-%j.out

set -euo pipefail

MANIFEST="${1:?usage: sbatch runner/slurm_eval.sh <manifest.yaml>}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -n "${VENV:-}" ]]; then
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
fi

echo "[slurm] host=$(hostname) manifest=$MANIFEST"
nvidia-smi --query-gpu=name --format=csv,noheader || true

EXTRA=()
[[ "${QUALITY:-0}" == "1" ]] && EXTRA+=(--quality)

python runner/eval_submission.py "$MANIFEST" "${EXTRA[@]}"

if [[ "${AUTO_PUBLISH:-0}" == "1" ]]; then
  echo "[slurm] publishing results.json ..."
  git add docs/data/results.json results/*.json 2>/dev/null || git add docs/data/results.json
  git commit -m "eval: $(basename "$MANIFEST") on $(hostname)" || echo "[slurm] nothing to commit"
  git push || echo "[slurm] git push failed (push manually)"
else
  echo "[slurm] done. Review + commit docs/data/results.json to publish."
fi
