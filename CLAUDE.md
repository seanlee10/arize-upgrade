# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An automated upgrade pipeline for a **self-hosted Arize AX cluster on EKS**. It watches the vendor's release page, gets two human approvals in chat, moves container images into ECR, runs the vendor's `arize.sh install`, and reports the result.

The thing to hold onto: **this tool upgrades a production cluster by running irreversible Postgres/Druid/gazette migrations with no rollback path.** Strictness that looks paranoid in this codebase is usually deliberate. Before softening a guard into a warning or a fallback, find out what it protects.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # first-time setup
.venv/bin/pytest -q                                          # full suite
.venv/bin/pytest tests/test_state.py -q                      # one file
.venv/bin/pytest tests/test_state.py::test_completed_runs_do_not_count -q   # one test
.venv/bin/arize-upgrade --help                               # the CLI the workflows call
```

Tests never touch the network or a cluster. Every external boundary is an injected callable (`fetch`, `post`, `run`) with a real default and a fake in tests — keep it that way rather than reaching for a mocking library.

## Architecture

Two GitHub Actions workflows are thin shells; all real logic lives in `src/arize_upgrade/` so it is testable without triggering an upgrade.

```
check-release.yml (cron)  →  upgrade.yml
                              announce → push-images → announce-images → install → record
                                         [env gate]                      [env gate]
```

`cli.py` is the only entry point the workflows call. It composes the other modules and writes `$GITHUB_OUTPUT`; its exit codes are the contract (0 = success or nothing to do, 1 = hard failure the workflow must surface).

### Five facts that explain most of the design

**1. The distribution bundle *is* the version.** The vendor's `arize.sh` hardcodes `VERSION` plus a table of 26 per-image `sha256` digests. There is no version string to bump — upgrading means fetching a new bundle.

**2. The download endpoint serves *latest only*.** `get_latest.sh` cannot be asked for a specific version. So the pipeline detects N, a human approves N, and a later job downloads "latest" — which is a different release if the vendor ships N+1 in between. `bundle.py` exists solely to turn that silent substitution into a loud abort, which is why it errors on zero bundles, on *more than one* bundle, on a directory missing `arize.sh`, and on any version mismatch.

**3. Approvals are GitHub Environments, not chat interactions.** A job declaring `environment: image-push` pauses until a reviewer approves in the GitHub UI. Every "action button" is therefore just a **link** button — which is the whole reason Slack and Teams are interchangeable. Nothing here runs an HTTPS endpoint or verifies request signatures.

**4. A run paused at an approval gate reports GitHub status `waiting`, not `in_progress`.** Since this pipeline's normal state is sitting at a gate for hours, `state.ACTIVE_STATUSES` must include `waiting` and `queued`. Omitting them means the daily cron dispatches a second upgrade while the first awaits a human. Relatedly, `upgrade_in_progress` returns `True` when `gh` fails — it fails *safe*, so a GitHub outage cannot green-light a concurrent upgrade.

**5. Provider symmetry is load-bearing, not cosmetic.** `slack.py`, `teams.py`, and `slack_webhook.py` must render the same `Notification` equivalently, because the user switches between them with one repo variable. All three prefix the same status icon for all three statuses. `slack_webhook.py` goes further than symmetry: it imports `render_blocks` from `slack.py` outright rather than re-rendering, so the two Slack providers cannot drift apart by construction. `messages.py` is the provider-agnostic composition layer and must carry neither provider's conventions — notably no markdown emphasis, since single asterisks are bold in Slack mrkdwn but italic in an Adaptive Card TextBlock.

### Module map

| Module | Responsibility |
|---|---|
| `versions.py` | `Version` — frozen, `order=True`, so comparison is numeric (`11.9.0 < 11.40.0`), never lexicographic |
| `releases.py` | Parses the **markdown twin** of the release page (`…/on-premise-releases.md`), far more stable than the rendered HTML |
| `state.py` | Deployed version as GitHub Releases tagged `deployed/<version>`; concurrency check |
| `bundle.py` | Locates and version-verifies the downloaded bundle |
| `messages.py` | Builds the four stage `Notification`s — provider-agnostic, no I/O |
| `notify/` | `base.py` types + `factory.py` dispatch on `NOTIFY_PROVIDER`, with `slack.py` / `teams.py` / `slack_webhook.py` adapters |

## Conventions that bite

- **`arize.sh` is always invoked `-y -q`.** `-y` is the only thing that skips `push-images`' blocking `Continue (y/n)?` prompt. Never pass `-v` — it echoes the rendered `values.yaml`, which contains private keys.
- **`values.yaml` is never committed.** It holds a GCP service-account key, two TLS private keys, the Postgres password, SMTP credentials and the hub JWT. Only `config/values.template.yaml` with `${VAR}` placeholders is tracked; the runner renders it with `envsubst` and must not log the result.
- **The Arize JWT is needed in two encodings.** `arize.sh` does `license=$(echo -n $hubJwt | base64 -d)`, so `values.yaml` wants the base64 form, while `get_latest.sh` wants the raw JWT in a Bearer header. Hence `ARIZE_HUB_JWT` and `ARIZE_HUB_JWT_RAW`.
- **`.gitignore` carries `!docs/` deliberately.** The user's global gitignore excludes `docs`, so removing that line silently stops tracking the spec and plan.
- **Zero parsed releases is always a hard failure.** A docs redesign must never be indistinguishable from "no new release".
- **`Notification` is frozen but deliberately not hashable** — `fields` is a dict. Don't "fix" that; nothing needs it as a dict key.
- **`kubectl` is pinned to the cluster ARN.** `arize.sh` runs `kubectl --cluster=$clusterName` where `clusterName` is the full EKS ARN, so `aws eks update-kubeconfig` must use `--alias` with that exact ARN.

## Design docs

`docs/superpowers/specs/` holds the design and its rationale; `docs/superpowers/plans/` holds the implementation plan. The spec is the authority — when the plan and the spec disagree, the spec wins.
