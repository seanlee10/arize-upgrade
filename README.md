# Arize Auto-Upgrade

Automated upgrade pipeline for a self-hosted Arize AX cluster on EKS, with two human approval gates in Slack or Microsoft Teams.

> **Status:** the Python core is complete and tested. The GitHub Actions workflows, the `values.yaml` template, and the runner scripts are still being implemented — see `docs/superpowers/plans/` for what has landed. Sections below marked _(pending)_ describe files that do not exist yet.

## How it works

1. **Daily at 09:00 UTC**, `check-release.yml` parses <https://arize.com/docs/ax/selfhosting/on-premise-releases.md> and compares the newest release against the deployed version.
2. If a newer release exists it dispatches `upgrade.yml`, which posts the release and every intervening **Upgrade Notes** section to chat with an **Approve image push** button.
3. After approval, images are pulled from `ch.hub.arize.com` and pushed to ECR.
4. Chat gets a second message with an **Approve install** button.
5. After approval, `./arize.sh install` runs, gated on `install-status`.
6. Chat gets the result with an **Open Arize** button, and a GitHub Release tagged `deployed/<version>` records the new state.

Approvals use **GitHub Environments**, so every button is a link into the run's approval page. That is why Slack and Teams are interchangeable — and why nothing here needs a public HTTPS endpoint or request-signature verification.

## Read this before running it

This tool upgrades a production cluster. Three properties are worth knowing up front:

- **There is no rollback.** Upgrades run irreversible Postgres, Druid, and gazette init jobs. A failure notifies loudly and stops; recovery is a human decision using `arize.sh backup-db-local` and `restore-from-*`.
- **It jumps straight to latest.** The vendor's `get_latest.sh` only ever serves the newest release, so intermediate versions cannot be pinned. Every intervening Upgrade Notes section is surfaced at approval time so a human sees the breaking changes before saying yes.
- **The approved version is verified after download.** Because "latest" is a moving target, the job re-checks that what it downloaded is what was approved, and aborts if a newer release landed mid-run.

## Setup

Nothing environment-specific is hardcoded anywhere in this repo — every cluster/account/region/URL value below comes from a GitHub Actions **Variable** or **Secret**. `config/values.template.yaml` is 100% `${VAR}` placeholders; `scripts/render-values.sh` fails closed if a required one is missing.

### 1. Repository variables

Non-secret. Two groups: the pipeline's own workflow variables, and the `ARIZE_*` variables that `scripts/render-values.sh` substitutes into `config/values.template.yaml` (see step 5).

**Workflow variables** (read directly by the Python CLI / workflows):

| Variable | Example | Purpose |
|---|---|---|
| `NOTIFY_PROVIDER` | `slack` | `slack` or `teams`. Exactly one; an unknown value is a hard error. |
| `SLACK_CHANNEL_ID` | `C0123456789` | Slack only. |
| `PUSH_REGISTRY` | `123456789012.dkr.ecr.us-east-1.amazonaws.com` | ECR registry host, used when composing chat messages. |
| `APP_BASE_URL` | `https://arize-app.example.com` | Linked from the result message. |
| `AWS_REGION` | `us-east-1` | |
| `EKS_CLUSTER_NAME` | `my-cluster` | Short name, for `aws eks update-kubeconfig`. |
| `EKS_CLUSTER_ARN` | `arn:aws:eks:us-east-1:123456789012:cluster/my-cluster` | Must equal `clusterName` in your values. |
| `DEPLOYED_VERSION` | `11.41.0` | Bootstrap only; ignored once a `deployed/*` Release exists. |

```bash
gh variable set NOTIFY_PROVIDER --body slack
gh variable set DEPLOYED_VERSION --body 11.41.0
```

The pipeline **never guesses** the deployed version. On the very first run there is no `deployed/*` Release, so `DEPLOYED_VERSION` must be seeded or the check fails with instructions.

**Values-template variables — required** (no default; `render-values.sh` refuses to run without every one of these):

| Variable | Example | `values.yaml` key |
|---|---|---|
| `ARIZE_CLUSTER_ARN` | `arn:aws:eks:us-east-1:123456789012:cluster/my-cluster` | `clusterName` — `kubectl` is pinned to this exact ARN |
| `ARIZE_REGION` | `us-east-1` | `region` |
| `ARIZE_GAZETTE_BUCKET` | `my-cluster-gazette-bucket` | `gazetteBucket` |
| `ARIZE_DRUID_BUCKET` | `my-cluster-druid-bucket` | `druidBucket` |
| `ARIZE_ORGANIZATION_NAME` | `my-org` | `organizationName` |
| `ARIZE_APP_BASE_URL` | `https://arize-app.example.com` | `appBaseUrl` |
| `ARIZE_EXP_BASE_URL` | `https://grpc.example.com` | `expBaseUrl` |
| `ARIZE_RW_BUCKET_ROLE_ARN` | `arn:aws:iam::123456789012:role/my-cluster-webidentity-role-rw` | `awsServiceAccountRoleRwBucket` |
| `ARIZE_PUSH_REGISTRY` | `123456789012.dkr.ecr.us-east-1.amazonaws.com` | `pushRegistry` |
| `ARIZE_GCP_PROJECT` | `my-gcp-project` | `gcpProject` |
| `ARIZE_SMTP_HOST` | `email-smtp.us-east-1.amazonaws.com` | `smtpHost` |
| `ARIZE_SMTP_SENDER_EMAIL` | `ops@example.com` | `smtpSenderEmail` |

**Values-template variables — optional** (applied automatically when unset; `render-values.sh` logs which defaults it applied):

| Variable | Default | `values.yaml` key |
|---|---|---|
| `ARIZE_CLOUD` | `aws` | `cloud` |
| `ARIZE_REPO_NAME` | `arize` | `repoName` |
| `ARIZE_CLUSTER_SIZING` | `test` | `clusterSizing` |
| `ARIZE_STORAGE_CLASS_AWS_STANDARD` | `gp3` | `storageClassAwsStandard` |
| `ARIZE_STORAGE_CLASS_AWS_SSD` | `gp3` | `storageClassAwsSsd` |
| `ARIZE_SMTP_PORT` | `587` | `smtpPort` |
| `ARIZE_SMTP_REQUIRE_TLS` | `true` | `smtpRequireTls` |
| `ARIZE_COLLECT_NODE_METRICS` | `true` | `collectNodeMetrics` |
| `ARIZE_ZONE_AWARE` | `false` | `zoneAware` |
| `ARIZE_ALYX_ENABLED` | `false` | `alyxEnabled` |
| `ARIZE_REALTIME_USE_LATEST_OFFSET` | `false` | `realTimeUseLatestOffset` |
| `ARIZE_REALTIME_MUTABLE_CUTOVER_DATE` | `3000-01-01T00:00:00Z` | `realTimeMutableCutoverDate` |
| `ARIZE_REALTIME_GLOBAL_CUTOVER_TIME` | `3000-01-01T00:00:00Z` | `realTimeGlobalCutoverTime` |
| `ARIZE_REALTIME_SPACE_CUTOVER_TIME` | `3000-01-01T00:00:00Z` | `realTimeSpaceCutoverTime` |
| `ARIZE_DATA_FABRIC_ENABLED` | `true` | `dataFabricEnabled` |
| `ARIZE_DATA_FABRIC_PERMISSIONS_CHECK_ENABLED` | `true` | `dataFabricPermissionsCheckEnabled` |
| `ARIZE_HISTORICAL_NODE_POOL_ENABLED` | `true` | `historicalNodePoolEnabled` |
| `ARIZE_ENABLE_CUSTOM_CODE_EVALS` | `true` | `enableCustomCodeEvals` |

### 2. Secrets

Set on **both** the `image-push` and `cluster-install` environments:

| Secret | Notes |
|---|---|
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Needs ECR push, `ecr:CreateRepository`, and EKS access. |
| `ARIZE_HUB_JWT_RAW` | The JWT as issued, for the distribution download. |
| `ARIZE_HUB_JWT` | The **base64** form, which goes into `values.yaml`. |
| `ARIZE_CIPHER_KEY`, `ARIZE_POSTGRES_PASSWORD` | |
| `ARIZE_SMTP_USER`, `ARIZE_SMTP_PASSWORD` | |
| `ARIZE_GCP_SA_KEY` | |
| `ARIZE_INTERNAL_TLS_CERT`, `ARIZE_INTERNAL_TLS_KEY` | |
| `ARIZE_FLIGHT_TLS_CERT`, `ARIZE_FLIGHT_TLS_KEY` | |

`ARIZE_HUB_JWT_RAW` and `ARIZE_HUB_JWT` are two encodings of the same credential: `arize.sh` does `license=$(echo -n $hubJwt | base64 -d)`, so the value in `values.yaml` is base64-encoded, while `get_latest.sh` wants the raw JWT in an `Authorization: Bearer` header.

`check-release.yml` additionally needs repository-level `SLACK_BOT_TOKEN` or `TEAMS_WEBHOOK_URL`.

### 3. Environments

Create two environments, each with **required reviewers**:

- `image-push` — gates pulling and pushing images
- `cluster-install` — gates touching the cluster

**Without reviewers configured the jobs run unattended and there are no approvals at all.** This is the single easiest thing to get wrong.

### 4. Chat

**Slack:** create an app with the `chat:write` bot scope, install it, invite it to the channel, then set `SLACK_BOT_TOKEN` (`xoxb-…`) and `SLACK_CHANNEL_ID`. All four messages of an upgrade thread under the first.

**Teams:** in the target channel add a **Workflows** flow from the "post to a channel when a webhook request is received" template, then set `TEAMS_WEBHOOK_URL`. Microsoft retired Office 365 Connectors, so the older `outlook.office.com/webhook/...` URLs are not the path here. Teams webhooks cannot thread, so each stage arrives as its own self-contained card.

### 5. Values template _(pending)_

`config/values.template.yaml` is generated from a real `values.yaml`:

```bash
python3 scripts/make-values-template.py /path/to/values.yaml
grep -c 'BEGIN PRIVATE KEY' config/values.template.yaml   # must be 0
```

Your live `values.yaml` contains a GCP service-account private key, two TLS private keys, the Postgres password, SMTP credentials and the hub JWT. It is gitignored and must never be committed. Only the template, with `${VAR}` placeholders, is tracked; the runner renders it with `envsubst` and never logs the result.

## Prerequisites this repo cannot solve

- The EKS API endpoint must be reachable from GitHub-hosted runners.
- The IAM principal must be mapped in EKS access entries with rights to install.
- A valid Arize hub JWT.

## Operational notes

- **Disk.** `pull-images` stages 26 container images through the local Docker daemon. `ubuntu-latest` has ~14 GB free on `/` but ~65 GB on `/mnt`, so `scripts/prepare-runner-disk.sh` _(pending)_ relocates Docker's `data-root` before the pull. If a future release still overflows, switch to `./arize.sh -y -q --skopeo load-remote-images`, which copies registry-to-registry and uses no local disk.
- **Concurrency.** A run paused at an approval gate reports GitHub status `waiting`. The scheduled check treats `waiting`, `queued` and `in_progress` alike as "an upgrade is active", and treats a failed `gh` call the same way, so neither a long approval wait nor a GitHub outage can trigger a second concurrent upgrade.
- **Approvals expire.** GitHub cancels a run awaiting approval after 30 days; the next scheduled check re-detects and re-dispatches.
- **Parsing, not an API.** The release notes are parsed from the docs site's markdown twin. Zero parsed releases is always a hard failure with an alert — a docs redesign must never look like "no new release".

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
```

Tests never touch the network or a cluster: every external boundary is an injected callable with a real default and a fake in tests. See `CLAUDE.md` for the architecture and the conventions worth knowing before changing anything.
