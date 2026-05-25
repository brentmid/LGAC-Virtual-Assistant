# Deployment Plan: Cloud Run + HTTPS (Issues #19 & #24)

**Created**: 2026-02-22
**Status**: Complete — deployed 2026-02-24; **test deployment decommissioned 2026-05-25**
**Issues**: [#19](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/19) (Cloud Run deployment), [#24](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/24) (HTTPS)

> ⚠️ **These were test credentials on a personal account, and the deployment has been shut down.**
> The Cloud Run service, the personal GCP project (`lgac-virtual-assistant`), and the Anthropic API key
> described below were a **temporary MVP test deployment**. They were **decommissioned on 2026-05-25** to
> stop billing before this repository was made public. **All credentials and resources referenced in this
> document are dead and must not be reused** — including the `lgac2026` shared password, the Anthropic API
> key, the GCP project, and the `*.run.app` service URL.
>
> This document is retained as a **reference runbook** for whoever stands the service back up. As part of the
> transition to Club IT (see `TRANSITION_PLAN.md`), Club IT must provision a **fresh GCP project, a new
> Anthropic API key, and new passwords** in their own accounts. The steps below are project-portable — only
> the project ID, account, and secret values change.

## Overview

Deploy the LGAC Virtual Assistant to Google Cloud Run. Cloud Run provides automatic HTTPS with managed TLS certificates, so issues #19 and #24 are resolved together. Scale-to-zero means no cost when idle.

## Prerequisites

### Tools (already installed)

| Tool | Version | Status |
|------|---------|--------|
| `gcloud` CLI | 533.0.0 | Installed at `~/bin/google-cloud-sdk/bin/gcloud` |
| `docker` CLI | 28.2.2 | Installed (daemon not needed — we use Cloud Build) |
| `podman` | 5.8.0 | Installed, VM running |
| `brew` | 5.0.14 | Available for any additional installs |

### gcloud Authentication — Dual Configuration

The original developer's `gcloud` had to stay authenticated to a separate **work account / work GCP project** (used by Claude Code for Vertex billing). A separate named `home` configuration was used for this project so both could coexist, and all deployment commands use `--configuration=home` to target the home account without switching the default. *(Club IT will use a single account and project of their own and can ignore this dual-configuration setup.)*

## Phase 1: GCP Project Setup (Manual — Brent)

Run each command below one at a time. Check off each step as it completes.

### 1.1 Create the `work` gcloud configuration (preserves current auth)

- [x] **Step 1**: Rename the current default config to `work`:
```bash
gcloud config configurations create work
```

- [x] **Step 2**: Set the work project:
```bash
gcloud config set project YOUR-WORK-PROJECT --configuration=work
```

- [x] **Step 3**: Copy existing auth to work config (set account):
```bash
gcloud config set account your-work-account@example.com --configuration=work
```

### 1.2 Create the `home` gcloud configuration

- [x] **Step 4**: Create the home configuration:
```bash
gcloud config configurations create home
```

- [x] **Step 5**: Log in with your home/club Google account:
```bash
gcloud auth login --configuration=home
```

### 1.3 Create the GCP project

- [x] **Step 6**: Create the project (project number: 477512975027):
```bash
gcloud projects create lgac-virtual-assistant --name="LGAC Virtual Assistant" --configuration=home
```

- [x] **Step 7**: Set the home configuration's default project:
```bash
gcloud config set project lgac-virtual-assistant --configuration=home
```

- [x] **Step 8**: Enable billing — **must be done in the browser**:
  - Go to https://console.cloud.google.com/billing
  - Make sure you're signed in with your home Google account (top-right avatar)
  - Link a billing account to the `lgac-virtual-assistant` project
  - (New Google Cloud accounts get $300 free credits)

### 1.4 Enable required APIs

- [x] **Step 9**: Enable APIs:
```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --configuration=home
```

### 1.5 Create Artifact Registry repository

- [x] **Step 10**: Create the Docker repo:
```bash
gcloud artifacts repositories create lgac-assistant --repository-format=docker --location=us-central1 --description="LGAC Virtual Assistant Docker images" --configuration=home
```

### 1.6 Store secrets in Secret Manager

- [x] **Step 11**: Store the Anthropic API key (replace with your actual key):
```bash
echo -n "sk-ant-YOUR-KEY-HERE" | gcloud secrets create anthropic-api-key --data-file=- --configuration=home
```

- [x] **Step 12**: Store the app password:
```bash
echo -n "CHOOSE-A-NEW-APP-PASSWORD" | gcloud secrets create app-password --data-file=- --configuration=home
```

- [x] **Step 13**: Store the admin password (replace with your chosen password):
```bash
echo -n "YOUR-ADMIN-PASSWORD" | gcloud secrets create admin-password --data-file=- --configuration=home
```

- [x] **Step 14**: Grant Cloud Run access to all secrets:
```bash
PROJECT_NUMBER=$(gcloud projects describe lgac-virtual-assistant --format='value(projectNumber)' --configuration=home) && for SECRET in anthropic-api-key app-password admin-password; do gcloud secrets add-iam-policy-binding $SECRET --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" --role="roles/secretmanager.secretAccessor" --configuration=home; done
```

### 1.7 Re-activate the work configuration

- [x] **Step 15**: Switch back to work as the default (so Claude Code keeps working):
```bash
gcloud config configurations activate work
```

## Phase 2: HTTPS Middleware (Code Change — Claude)

Add FastAPI middleware to `src/lgac_assistant/app.py` that:

1. Checks `X-Forwarded-Proto` header (set by Cloud Run's TLS proxy)
2. Redirects HTTP → HTTPS when behind the proxy
3. Adds `Strict-Transport-Security` (HSTS) header to all responses
4. Skips redirect for `localhost` / `127.0.0.1` (local dev stays HTTP)

This is ~20 lines of code. No additional dependencies needed.

### Acceptance criteria for #24
- [x] HTTPS enforced in production (Cloud Run handles TLS termination)
- [x] HTTP → HTTPS redirect when `X-Forwarded-Proto: http` is detected
- [x] HSTS header added to responses in production
- [x] Local dev (`localhost`) continues to work over HTTP
- [x] Documented in README

## Phase 3: Build & Push Container Image

### Why Cloud Build (not local build)

- Your Mac is ARM64 (Apple Silicon); Cloud Run requires linux/amd64
- Cloud Build runs remotely on Google's infrastructure — no local Docker daemon needed
- Avoids cross-architecture emulation issues

### Important: `rag-docs/` must be present

The Dockerfile runs `python scripts/ingest_docs.py` at build time, which reads from `rag-docs/`. This directory is gitignored but must be present when submitting to Cloud Build. The `gcloud builds submit` command uploads the entire working directory (respecting `.gcloudignore`), so `rag-docs/` will be included as long as it exists locally.

Create a `.gcloudignore` file to exclude unnecessary files from the upload:
```
.git
.venv
__pycache__
*.pyc
.env
chroma_data/
feedback.json
.pytest_cache
.ruff_cache
```

Note: do NOT add `rag-docs/` to `.gcloudignore` — it must be uploaded for the build.

### Build command

- [x] **Step 16**: Build and push the image via Cloud Build:
```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/lgac-virtual-assistant/lgac-assistant/lgac-assistant:latest --timeout=1200 --configuration=home
```

This uploads the source, builds the Docker image on Google's servers (linux/amd64), and pushes it to Artifact Registry. The 1200s timeout allows for the pip install + index build steps.

## Phase 4: Deploy to Cloud Run

- [x] **Step 17**: Deploy to Cloud Run:
```bash
gcloud run deploy lgac-assistant --image us-central1-docker.pkg.dev/lgac-virtual-assistant/lgac-assistant/lgac-assistant:latest --region us-central1 --platform managed --allow-unauthenticated --cpu 1 --memory 1Gi --min-instances 0 --max-instances 2 --port 9247 --set-secrets "ANTHROPIC_API_KEY=anthropic-api-key:latest,APP_PASSWORD=app-password:latest,ADMIN_PASSWORD=admin-password:latest" --configuration=home
```

### What `--allow-unauthenticated` means

This allows anyone on the internet to hit the URL. The app handles its own auth via the shared password (`APP_PASSWORD`). Cloud Run's IAM auth is separate — we skip it because our users don't have Google accounts.

### Expected output

```
Service [lgac-assistant] revision [lgac-assistant-00001-xxx] has been deployed
and is serving 100 percent of traffic.

Service URL: https://lgac-assistant-477512975027.us-central1.run.app
```

## Phase 5: Verify

### 5.1 Health check
```bash
curl https://lgac-assistant-477512975027.us-central1.run.app/api/health
# Expected: {"status":"ok","documents_indexed":205}
```

### 5.2 HTTPS verification
```bash
# Should get 301 redirect
curl -I http://lgac-assistant-477512975027.us-central1.run.app/
# (Cloud Run itself handles this — HTTP is not exposed on *.run.app domains)

# Should work
curl -I https://lgac-assistant-477512975027.us-central1.run.app/
```

### 5.3 Full QA

Open the HTTPS URL in a browser and run through the QA checklist in CLAUDE.md:
1. Password gate (wrong password → error, correct password → chat)
2. Club question ("What is the dress code for golf?")
3. Follow-up with context ("What about dining?")
4. Off-topic rejection ("What's the weather today?")
5. Specific policy with source citation ("What are the annual dues?")
6. Vague question ("Tell me about the club")
7. Unknown topic ("What is the wifi password?")
8. Feedback submission ("feedback: Great answer!")
9. Markdown rendering in responses

### 5.4 Admin page
- Navigate to `https://lgac-assistant-477512975027.us-central1.run.app/admin`
- Log in with the admin password
- Verify feedback records appear

## Phase 6: Document & Close Issues

1. Update README.md with deployment section
2. Close GitHub issue #19 (Cloud Run deployment)
3. Close GitHub issue #24 (HTTPS)

## Subsequent Deploys

When code or documents change, redeploy with:

```bash
cd ~/bin/LGAC-Virtual-Assistant

# Rebuild image (if docs changed, rag-docs/ must be present locally)
gcloud builds submit \
  --tag us-central1-docker.pkg.dev/lgac-virtual-assistant/lgac-assistant/lgac-assistant:latest \
  --configuration=home

# Deploy new revision
gcloud run deploy lgac-assistant \
  --image us-central1-docker.pkg.dev/lgac-virtual-assistant/lgac-assistant/lgac-assistant:latest \
  --region us-central1 \
  --configuration=home
```

Cloud Run deploys new revisions with zero downtime (traffic shifts after the new revision passes health checks).

## Cost Estimate

| Component | Estimated Cost |
|-----------|---------------|
| Cloud Run (scale-to-zero) | ~$0/month when idle; pennies per request |
| Artifact Registry | ~$0.10/GB/month for stored images |
| Cloud Build | 120 free min/day; builds take ~5 min each |
| Secret Manager | Free tier covers this usage |
| Anthropic API | ~$0.01-0.03 per query (Claude Sonnet 4.6) |

For an MVP with light tester traffic, expect **< $5/month** total GCP cost (Anthropic API cost is separate and depends on query volume).
