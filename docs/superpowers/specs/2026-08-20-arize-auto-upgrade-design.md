# Arize Self-Hosted Auto-Upgrade — Design

**Date:** 2026-08-20
**Status:** Approved for planning

## Problem

Arize ships self-hosted releases roughly weekly. Upgrading the cluster today is
manual: notice the release, download the distribution, move 26 container images
into ECR, and run `./arize.sh install`. The work is repetitive but not safe to
fully automate — an upgrade runs Postgres, Druid, and gazette init jobs and
cannot be rolled back cleanly.

This repo automates everything except the two decisions that need a human, and
puts those decisions in chat.

## Goals

1. Detect new releases on <https://arize.com/docs/ax/selfhosting/on-premise-releases> daily.
2. Notify a chat channel and wait for explicit human approval before pushing images.
3. Move the release's images into a private Amazon ECR registry.
4. Notify again and wait for explicit human approval before touching the cluster.
5. Run `./arize.sh install` and gate success on `install-status`.
6. Report the outcome with a link that opens the Arize app.
7. Work against either Slack or Microsoft Teams, switchable without code changes.

## Non-Goals

- **No rollback.** A failed install notifies loudly and stops. Reverting is a
  human decision using `arize.sh backup-db-local` / `restore-from-*`.
- **No cluster provisioning.** EKS, S3 buckets, and IAM already exist.
- **No stepping through intermediate versions.** The policy is jump-to-latest,
  with all intervening Upgrade Notes surfaced in the approval message.

## Background: what `arize.sh` actually does

Findings from `arize-distribution-11.37.1/arize.sh` (1876 lines) and
`arize-distribution-11.41.0/`. These constrain the design and are easy to get
wrong from the public docs alone.

**The distribution bundle *is* the version.** `arize.sh` hardcodes
`a pinned build id` and a table of 26 per-image `sha256` digests
(`image digest table`). There is no version string to bump. Upgrading means
fetching a new bundle:

```
curl -H "Authorization: Bearer $JWT" "https://ch.hub.arize.com/dist/get_latest.sh" | sh -
```

Verified: that URL returns `401` unauthenticated. It serves **latest only** —
there is no version-pinned download. The bundle tar is **9.3 MB** (272 entries:
`arize.sh`, `arize-operator-chart.tgz`, `terraform/`, `examples/`, `docs/`). The
6.4 GB `.tgz` present in a local extracted folder is a separate air-gapped image
archive and is *not* part of this download.

**Consequence:** the workflow cannot request version *N*. It downloads latest,
reads the version from the directory name `arize-distribution-X.Y.Z`, and
**aborts if that does not equal the target version** detected from the release
page. This closes the race where a newer release lands between detection and
install.

**Parameter resolution order** (`default loading` → `values loading` → `argument parsing`,
lines 337–398): built-in defaults, then `values.yaml`, then `key=value` CLI
arguments. Relevant defaults:

| Parameter | Default | Notes |
|---|---|---|
| `arizeCentralRegistry` | `ch.hub.arize.com` | Source registry |
| `pushRegistry` | *(empty)* | Must be set for ECR |
| `repoName` | `arize` | |
| `repoSubdir` | *(empty)* | |
| `imagePullMode` | *(empty)* | Empty ⇒ path style `$pushRegistry/$repoName/$image:$tag` |
| `namespaceArize` | `arize` | |
| `namespaceOperator` | `arize-operator` | |
| `helmNamespace` | `default` | |
| `tag` | `$VERSION` | The bundle's baked-in git hash |

**`-y` is required for CI.** `the push step()` (line 714) prints
`"You are about to push images to registry ... Continue (y/n)?"` and blocks on
`read` when `INTERACTIVE=true`. `-y` sets `INTERACTIVE=false` and is the only
thing that makes the step unattended. `-q` suppresses the banner; `-t <secs>`
sets the global timeout (default 1800).

**ECR is a first-class target.** `the push step()` (lines 753–761) already runs
`aws ecr describe-repositories || aws ecr create-repository
--image-scanning-configuration scanOnPush=true` per image. The workflow does not
need to pre-create repositories.

**Disk is the real constraint.** `the pull step()` (line 645) pulls each of 26
images into the local Docker daemon; `the push step()` re-tags and pushes from
there. A GitHub-hosted `ubuntu-latest` runner has ~14 GB free on `/` but a much
larger ephemeral volume at `/mnt` (~65 GB). Mitigation is mandatory: remap
Docker's `data-root` to `/mnt` before pulling. See "Runner disk" below.

**`install` is `helm upgrade --install`.** `the install step()` (line 508) runs
`helm upgrade --install --namespace $helmNamespace -f $VALUE_FILE arize-op
arize-operator-chart.tgz`, then the CR chart. It is idempotent and is the same
command for a fresh install and an upgrade.

**`kubectl` is pinned to the cluster name.** `argument parsing()` sets
`the cluster arguments`, and `clusterName`
is the full EKS ARN. The kubeconfig entry must therefore be aliased to that exact
ARN.

**`install-status` is a real operation.** It waits for the postgres, gazette, and
druid init jobs to reach `Completed` and for all statefulsets and deployments to
reach full readiness. It is the post-install health gate.

**`check_cluster()`** aborts if `clusterName` in `values.yaml` does not match the
existing Helm release — a useful built-in guard against pointing at the wrong
cluster.

## Architecture

Two GitHub Actions workflows. All non-trivial logic lives in a Python package so
it is testable without triggering a cluster upgrade; the YAML stays thin.

```
check-release.yml  (cron)
        │  new version detected
        ▼
upgrade.yml
   announce ──▶ push-images ──▶ announce-images ──▶ install ──▶ record
                [env gate]                          [env gate]
```

### Approval mechanism

Approvals use **GitHub Environments with required reviewers**. A job declaring
`environment: image-push` pauses before its first step until a reviewer approves
in the GitHub UI. The chat message posted by the preceding job carries a link
button to that run's approval page.

This means every "action button" is a **link**, which is why Slack and Teams are
interchangeable: Slack Block Kit `button` with a `url` and Teams Adaptive Card
`Action.OpenUrl` render identically in effect. No public HTTPS endpoint, no
request-signature verification, and no interactivity service to operate.

### Workflow 1: `check-release.yml`

Triggers: `schedule: cron '0 9 * * 1-5'` (09:00 UTC, weekdays) and
`workflow_dispatch`.

1. Fetch the release page and parse H1 headings of the form
   `Release X.Y.Z (YYYY-MM-DD)`.
2. **If zero versions parse, post an alert and fail the job.** A docs redesign
   must never be indistinguishable from "no new release."
3. Read the deployed version from the newest GitHub Release tagged
   `deployed/<version>`. **Bootstrap:** if no such Release exists, fall back to
   the repo variable `DEPLOYED_VERSION`; if that is also unset, post an alert
   explaining how to seed it and exit non-zero. The automation never guesses the
   currently deployed version.
4. If no newer version exists, exit 0 quietly.
5. If an `upgrade.yml` run is already in progress, log and exit 0.
6. Otherwise dispatch `upgrade.yml` with `target_version` only.

Upgrade Notes are **not** passed as a workflow input — several releases' worth of
notes can approach the `workflow_dispatch` payload limit. The `announce` job
re-fetches the release page and derives the notes itself, using the same
`releases.py` parser.

### Workflow 2: `upgrade.yml`

Triggers: `workflow_dispatch` with a single input, `target_version` (required).
Concurrency: `group: arize-upgrade`, `cancel-in-progress: false`.

| # | Job | Environment | Responsibility |
|---|---|---|---|
| 1 | `announce` | — | Post the parent message: target version, currently deployed version, aggregated Upgrade Notes, and an *Approve image push* link button. Outputs `thread_ref`. |
| 2 | `push-images` | `image-push` | Prepare runner disk; render `values.yaml`; download and version-verify the bundle; `./arize.sh -y -q pull-images`; `./arize.sh -y -q push-images`. |
| 3 | `announce-images` | — | Reply: images are in ECR, plus an *Approve install* link button. |
| 4 | `install` | `cluster-install` | Render `values.yaml`; download and version-verify the bundle; `aws eks update-kubeconfig`; `./arize.sh -y -q -t 3600 install`; `./arize.sh -y -q install-status`. |
| 5 | `record` | — | `if: always()`. Reply with the outcome and an *Open Arize* button pointing at `appBaseUrl`. On success create GitHub Release `deployed/<version>`; on failure open an Issue linking the run. |

Jobs 2 and 4 each re-download the bundle. At 9.3 MB this is cheaper and less
error-prone than passing it between runners as an artifact.

### Runner disk

`push-images` runs this before pulling, as a dedicated step:

1. `sudo systemctl stop docker`
2. Write `/etc/docker/daemon.json` with `{"data-root": "/mnt/docker"}`
3. `sudo mkdir -p /mnt/docker && sudo systemctl start docker`
4. Log `df -h /mnt` so failures are diagnosable from the run log

Uncompressed, 26 images are expected to exceed the ~14 GB free on `/`. `/mnt`
provides roughly 65 GB. If a future release still overflows, the documented
fallback is `./arize.sh -y -q --skopeo load-remote-images`, which copies
registry-to-registry (`skopeo copy docker://src docker://dest`, line 802) and
uses no local disk at all.

The job also runs `docker image prune -af` on completion.

## Notification layer

A `Notification` is built once, provider-agnostically, then rendered per
provider. Workflows never branch on the provider.

```python
@dataclass(frozen=True)
class Button:
    label: str
    url: str

@dataclass(frozen=True)
class Notification:
    title: str
    fields: dict[str, str]      # e.g. {"Current": "11.41.0", "Target": "11.43.0"}
    body: str | None            # markdown; used for Upgrade Notes
    buttons: list[Button]
    status: Literal["info", "success", "failure"]
```

```python
class Notifier(Protocol):
    def send(self, n: Notification, reply_to: str | None = None) -> str | None:
        """Post a notification. Returns a thread reference if the provider
        supports threading, else None."""
```

- **`SlackNotifier`** — `chat.postMessage` with a bot token. Renders Block Kit.
  Returns the message `ts`; later calls pass it as `thread_ts` so the whole
  upgrade lives in one thread.
- **`TeamsNotifier`** — POSTs an Adaptive Card to a Power Automate Workflows
  incoming webhook URL. Returns `None`; Teams webhooks cannot thread, so the four
  messages appear as standalone cards. Each card therefore restates the target
  version and carries the run link, so a card is self-contained out of context.

Selection is the repo variable `NOTIFY_PROVIDER` (`slack` | `teams`), read by a
factory. Exactly one provider is active. An unrecognized value is a hard error,
not a silent no-op.

Secrets: `SLACK_BOT_TOKEN` + `SLACK_CHANNEL_ID`, or `TEAMS_WEBHOOK_URL`. Only the
selected provider's secrets need to be set.

## Configuration and secrets

The live `values.yaml` contains `hubJwt`, `cipherKey`, `postgresPassword`, SMTP
credentials, a GCP service-account private key, and two TLS private keys. **It is
not committed.**

`config/values.template.yaml` is committed and holds the full structure with
non-secret values inline and `${VAR}` placeholders for secret fields. The runner
renders it with `envsubst` into a working `values.yaml`, which is never uploaded
as an artifact and never logged.

Two additions to the current configuration, both needed to move from connected
mode to ECR:

```yaml
pushRegistry: "<aws-account-id>.dkr.ecr.<region>.amazonaws.com"
repoName: "arize"
```

The account and region are derived from the existing `clusterName` ARN
(`arn:aws:eks:<region>:<aws-account-id>:cluster/<cluster-name>`) and `region`.
`repoSubdir` stays empty and `imagePullMode` stays unset, giving ECR repositories
named `arize/<image>` — matching the existing defaults.

**Rotation note:** the secrets currently in the working `values.yaml` were
exposed during design and should be rotated independently of this work.

## Python package

```
src/arize_upgrade/
  releases.py   parse the release page into [Release(version, date, notes)]
  versions.py   semver comparison; select target; slice notes between versions
  state.py      read/write deployed version via GitHub Releases
  notify/
    base.py     Notification, Button, Notifier protocol
    slack.py    Block Kit renderer + chat.postMessage
    teams.py    Adaptive Card renderer + webhook POST
    factory.py  NOTIFY_PROVIDER dispatch
  cli.py        subcommands invoked by the workflows
```

CLI surface:

- `arize-upgrade check` — detect, compare, emit `target_version` and notes to
  `$GITHUB_OUTPUT`; alert and fail on parse failure.
- `arize-upgrade notify --stage <announce|images|result> ...` — build and send.
- `arize-upgrade verify-bundle --dir <path> --expect <version>` — assert the
  downloaded bundle matches the target.
- `arize-upgrade record --version <v> --status <ok|fail>` — cut the Release or
  open the Issue.

## Testing

Unit tests (pytest), no network, no cluster:

- `releases.py` against a committed HTML fixture of the real release page —
  including the zero-versions-parsed failure path.
- `versions.py` — ordering, equality, "already current", multi-version gaps, and
  the notes slice between two versions.
- `notify/slack.py` and `notify/teams.py` — snapshot the rendered Block Kit and
  Adaptive Card JSON; assert buttons carry the right URLs; assert Slack threads
  and Teams does not.
- `notify/factory.py` — correct provider selected; unknown value raises.
- `verify-bundle` — matching version passes, mismatched version exits non-zero.

Workflow YAML is validated with `actionlint`. Shell steps run under `set -euo pipefail`.

## Prerequisites (documented in README, outside this repo's control)

- EKS API endpoint reachable from GitHub-hosted runners.
- The IAM principal behind `AWS_ACCESS_KEY_ID` mapped in EKS access entries with
  rights to install, and holding ECR push + `ecr:CreateRepository`.
- A valid Arize `hubJwt`.
- A Slack app with `chat:write` **or** a Power Automate Workflows webhook URL.
- GitHub Environments `image-push` and `cluster-install`, each with required
  reviewers.

## Decisions and rationale

| Decision | Rationale |
|---|---|
| GitHub Environment approvals over interactive chat buttons | No public endpoint, no signature verification, no service to run. Approval identity and audit trail come free. Works identically for Slack and Teams. |
| Jump straight to latest | `get_latest.sh` only serves latest, so stepping through versions is not possible without version-pinned downloads. Mitigated by surfacing all intervening Upgrade Notes at approval time. |
| Re-download the bundle per job | 9.3 MB. Cheaper and simpler than cross-job artifacts. |
| Version-verify after download | `get_latest.sh` is a moving target; without this, a release landing mid-run would install something nobody approved. |
| `pull-images` + `push-images` over `load-remote-images --skopeo` | Explicitly chosen. The `/mnt` data-root remap is what makes it viable; skopeo remains the documented fallback. |
| Deployed version in GitHub Releases | Immutable, timestamped, no extra infrastructure, and readable via `gh` from any job. |
| One provider at a time | Halves the failure surface versus fan-out; switching is a one-line repo-variable change. |
| No rollback in v1 | Upgrades run irreversible DB migration jobs. A pretend rollback is more dangerous than none. |

## Open risks

1. **Release page structure is scraped, not an API.** Mitigated by failing loudly
   on zero parses. A redesign will need a fixture and parser update.
2. **Long-lived IAM keys** are stored as environment secrets. Scoped to the
   `cluster-install` and `image-push` environments so they are unavailable to
   unapproved jobs. OIDC remains the better option if EKS access entries allow it.
3. **Image set growth** could eventually exceed even `/mnt`. Fallback documented.
4. **Approval expiry.** GitHub cancels a run awaiting approval after 30 days; the
   next scheduled check re-detects and re-dispatches.
