# LOG Acceleration Leaderboard

An internal, EQC-style inference-acceleration leaderboard. Team members
submit an **engine** (an EQC-style Docker image serving `Qwen/Qwen3.5-4B`
on port 8080); we run it on a **cluster GPU**, measure latency, and
publish the ranking as a **static site on GitHub Pages**.

Modeled on the AdaptFM Efficient-Qwen competition board
(<https://d1krc5fcnf73gi.cloudfront.net/>), but the numbers come from our
own cluster.

**🔗 Live board: <https://LOG-postech.github.io/log_acceleration_leaderboard/>**

```
┌─ submissions/<team>/submission.yaml   (points at a Docker image)
│
├─ runner/  (on a GPU node, via SLURM)
│    docker run → wait /ping → latency sweep → speedup vs baseline
│    → results/<team>__<id>.json → rebuild docs/data/results.json
│
└─ docs/  (GitHub Pages root) ── static site renders docs/data/results.json
```

## Ranking metric

Mean latency **speedup** vs. the dense baseline across three categories,
gated by quality (same shape as EQC):

| Category | Prompt tok | Output tok |
|---|---|---|
| Short | 64 | 128 |
| Medium | 2,048 | 256 |
| Long | 8,192 | 256 |

`speedup(cat) = baseline_median(cat) / measured_median(cat)`, averaged
over the three. Harness: 5 warmup + 50 measured runs, median, against
`POST /v1/completions`.

> ⚠️ **Speedup is only comparable within the same (GPU, model).** Unlike EQC
> (fixed A10G), our cluster has **A100 / PRO6000 / 3090**, and more models
> will be added over time. Baselines are stored **per (model, GPU)** in
> [`docs/data/config.json`](docs/data/config.json), each result records its
> GPU and model, and the leaderboard renders **a separate, independently
> ranked board per (GPU, model)**. Calibrate each (GPU, model) once with
> that model's dense image (see below).

Quality gates (MMLU-Pro ≥ 0.621, IFEval ≥ 0.814, GPQA-Diamond ≥ 0.630)
are shown as ⏳ *pending* — they'll be evaluated later on a sampled subset
(wire into [`runner/bench_quality.py`](runner/bench_quality.py)). A gate
`fail` marks a submission invalid and drops it from the ranking.

## The site

Two views, both organized as **model sub-tab → per-GPU boards** (pick a
model; each GPU gets its own board because baselines differ):

- **Leaderboard** ([`index.html`](docs/index.html)) — best valid
  submission per team, ranked within each (GPU, model) board.
- **All submissions** ([`submissions.html`](docs/submissions.html)) —
  every evaluated run (duplicates and quality-failed rows included,
  no rank; failed rows are struck through).

## Quickstart

### Preview the site locally

```bash
cd docs && python -m http.server 8000   # → http://localhost:8000
```

The page reads `docs/data/config.json` + `docs/data/results.json`
(seeded with example rows so it renders immediately).

### Add + evaluate a submission

```bash
# 1. write a manifest (copy the example)
cp -r submissions/example-team submissions/my-team
$EDITOR submissions/my-team/submission.yaml     # set team/id/image[/image_tar]

# 2. run it on a GPU node
pip install -r requirements.txt                 # PyYAML; needs docker CLI + a GPU
sbatch --partition=A100 runner/slurm_eval.sh submissions/my-team/submission.yaml
#   or directly on a GPU box:
python runner/eval_submission.py submissions/my-team/submission.yaml

# 3. publish
git add docs/data/results.json && git commit -m "eval: my-team" && git push
```

`eval_submission.py` writes a raw result to `results/<team>__<id>.json`
and rebuilds `docs/data/results.json`. Rebuild by hand any time with
`python runner/update_results.py`.

### Calibrate a baseline (once per GPU × model)

Run that model's **unoptimized dense** image so speedups are meaningful:

```bash
python runner/eval_submission.py submissions/baseline/dense.yaml --baseline
```

This stores the medians under `baselines[model][gpu]` in
`docs/data/config.json`. Add a model later by listing it in `config.json`
(`models`) and setting each submission's `model:` field.

## Publish on GitHub Pages

This repo serves the site from the **`/docs` folder on `main`** — no CI
needed. Already enabled here; to reconfigure:

1. Repo **Settings → Pages**
2. **Source**: *Deploy from a branch*
3. **Branch**: `main`, **Folder**: `/docs` → Save

Live at <https://LOG-postech.github.io/log_acceleration_leaderboard/>.
Every push that changes `docs/` redeploys it (~1 min).

> Free GitHub Pages requires the repo to be **public**. This repo is
> public (code + result JSON only — no weights, images, or secrets; those
> are `.gitignore`d). Switching it private disables Pages unless the org
> has a paid plan.

## Layout

```
docs/                 GitHub Pages root (static site)
  index.html            leaderboard — model sub-tabs → per-GPU boards (ranked)
  submissions.html      all runs — model sub-tabs → per-GPU boards (no rank)
  assets/{app.js,style.css}
  data/config.json      SOURCE OF TRUTH: baselines[model][gpu], thresholds, models
  data/results.json     rendered data: groups (boards) + submissions (regenerated)
runner/
  eval_submission.py    orchestrator (docker → benchmark → result)
  container.py          docker lifecycle (load/run/health/rm)
  bench_latency.py      latency sweep vs /v1/completions
  bench_quality.py      quality gates (placeholder → sampling later)
  update_results.py     merge raw results → docs/data/results.json
  config.py             loads config.json, GPU detection, baseline lookup
  slurm_eval.sh         sbatch wrapper
submissions/<team>/submission.yaml   one manifest per submission
results/              raw per-submission JSON (gitignored)
```

The latency methodology mirrors `eqc/model_eval/efficiency/` so an
existing EQC submission image works here unchanged.
