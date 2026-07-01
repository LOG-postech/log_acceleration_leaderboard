# Submissions

Each submission is a folder `submissions/<team>/` containing a
`submission.yaml` manifest that points at an **EQC-style Docker image**.

## The engine contract (port 8080)

The image must serve, on port **8080**:

| Endpoint | Method | Used by |
|---|---|---|
| `/ping` | GET | health — return 200 only when the model can serve |
| `/v1/completions` | POST | **latency benchmark** (raw prompt, OpenAI-compatible) |
| `/v1/chat/completions` | POST | quality gates (OpenAI chat; used later) |
| `/invocations` | POST | generic |

This is the same contract as the AdaptFM Efficient-Qwen container, so an
EQC submission image works here unchanged. The reference packaging lives
in `eqc/submission/` (Dockerfile + `serve/my_serve.py`).

## Manifest fields

See [`example-team/submission.yaml`](example-team/submission.yaml).

| Field | Required | Meaning |
|---|---|---|
| `team` | ✅ | team name shown on the board |
| `submission_id` | ✅ | unique id per team (result filename key) |
| `image` | ✅ | docker tag the runner will `docker run` |
| `display_name` | | label under the team name |
| `submitter` | | who submitted |
| `model` | | model the engine serves (default from `config.json`); boards split per model |
| `image_tar` | | path to `image.tar.gz`; `docker load`ed before run |
| `port` | | container port (default 8080) |
| `startup_timeout_s` | | health-check timeout (default 900) |
| `docker_args` | | extra args for `docker run` |
| `notes` | | free text |

## How it gets scored

1. Add `submissions/<team>/submission.yaml` (and stage the image / tarball
   somewhere the cluster node can reach).
2. On a GPU node: `sbatch --partition=A100 runner/slurm_eval.sh submissions/<team>/submission.yaml`
3. The runner starts the container, waits for `/ping`, runs the latency
   sweep (short/medium/long × 5 warmup + 50 measured, median), computes
   speedup vs. this **(GPU, model)**'s dense baseline, and rebuilds
   `docs/data/results.json`.
4. Commit + push → GitHub Pages redeploys the boards.

**Speedup is only comparable within the same (GPU, model)** — the
leaderboard shows a separate, independently-ranked board per (GPU, model).
Calibrate a (GPU, model) baseline once with that model's dense image:
`python runner/eval_submission.py submissions/baseline/dense.yaml --baseline`.

Quality gates (MMLU-Pro / IFEval / GPQA-Diamond) show as ⏳ *pending*
until the sampling-based quality eval is wired into
[`runner/bench_quality.py`](../runner/bench_quality.py).
