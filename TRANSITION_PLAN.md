# Transition Plan — LGAC Virtual Assistant

**Created**: 2026-05-25
**Audience**: Club IT staff or contracted vendor who will own and operate this system
**Closes**: [#44](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/44)
**Current state**: MVP, deployed to Google Cloud Run, single shared password, in-memory sessions

This document is the handoff guide for taking the LGAC Virtual Assistant from a developer-run MVP to a club-owned, production-grade service. It is written for a technical reader. It covers what exists today, the decisions the club must make (ownership, accounts, billing), and a phased path to production with effort and cost estimates.

---

## 1. What this system is

A Retrieval-Augmented Generation (RAG) Q&A chatbot. Club members ask questions in plain language; the assistant answers **only** from a fixed set of club documents (13 PDFs/DOCX: dress code, dues, rules, hours, membership, etc.). It does not browse the web and is instructed to decline off-topic questions and to never fabricate answers.

**How it works, end to end:**

1. **Offline ingestion** (`scripts/ingest_docs.py`) reads the source documents, extracts and cleans text, splits it into ~800-token chunks, embeds each chunk locally with the `all-MiniLM-L6-v2` model, and stores the vectors in an embedded ChromaDB index. This runs at **Docker build time** — the index is baked into the image, not built at runtime.
2. **At query time** (`src/lgac_assistant/rag.py`) the user's question is embedded, the top-5 most similar chunks are retrieved, and a prompt (system instructions + retrieved context + recent conversation + question) is sent to the **Claude Sonnet 4.6** API. The answer plus source-document citations is returned.

**Tech stack:** Python 3.11+, FastAPI/Uvicorn, ChromaDB (embedded), Anthropic Claude API, PyMuPDF + pdfplumber + python-docx for extraction, vanilla HTML/CSS/JS frontend, Docker, Google Cloud Run.

**Codebase map** (see `CLAUDE.md` for full detail):

| Path | Responsibility |
|------|----------------|
| `src/lgac_assistant/config.py` | Settings loaded from environment (`.env`) |
| `src/lgac_assistant/ingest.py` | PDF/DOCX extraction + chunking |
| `src/lgac_assistant/vectorstore.py` | ChromaDB wrapper |
| `src/lgac_assistant/rag.py` | Retrieval + Claude call |
| `src/lgac_assistant/prompts.py` | System prompt and guardrails |
| `src/lgac_assistant/sessions.py` | In-memory session manager (⚠️ ephemeral) |
| `src/lgac_assistant/feedback.py` | JSON-file feedback storage (⚠️ ephemeral) |
| `src/lgac_assistant/app.py` | FastAPI routes, static files, HTTPS middleware |
| `scripts/ingest_docs.py` | CLI that builds the vector index |
| `static/` | Chat UI + admin feedback page |
| `rag-docs/` | Source documents — **gitignored, not in the repo** |
| `tests/` | 66 tests |

---

## 2. Current deployment (as handed off)

- **Platform**: Google Cloud Run, region `us-central1`, project `lgac-virtual-assistant` (now deleted), owned by the original developer's personal Google account.
- **URL**: https://lgac-assistant-477512975027.us-central1.run.app
- **Sizing**: 1 CPU, 1 GB RAM, scale 0–2 instances, port 9247, `--allow-unauthenticated` (Cloud Run IAM is open; the **app** enforces its own password).
- **HTTPS**: automatic via Cloud Run managed TLS, plus app-side HTTP→HTTPS redirect and HSTS middleware.
- **Secrets**: `ANTHROPIC_API_KEY`, `APP_PASSWORD`, `ADMIN_PASSWORD` stored in Google Secret Manager and injected at deploy time.
- **Deploy process**: build with Cloud Build (remote, linux/amd64), then `gcloud run deploy`. Full runbook in `DEPLOYMENT_PLAN.md`.
- **Cost today**: < $5/month GCP (scale-to-zero) + Anthropic API at ~$0.01–0.03 per query.

⚠️ The deployment currently lives under a **personal Google account and a personal Anthropic account**. Transferring those is the central act of this handoff (Section 4).

---

## 3. Honest assessment of the MVP — what is NOT production-ready

These are deliberate MVP shortcuts. Each maps to an open GitHub issue. They must be addressed before this serves the full membership.

| # | Limitation | Why it matters in production | Issue |
|---|-----------|------------------------------|-------|
| 1 | **Single shared password** for all members | No per-user identity, no revocation, password leaks to everyone at once | [#16](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/16) |
| 2 | **Sessions in memory** | All conversations lost on restart/redeploy; breaks with >1 instance | [#17](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/17) |
| 3 | **No rate limiting** | One user (or a bot) can run up unbounded Anthropic API cost | [#18](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/18) |
| 4 | **No monitoring / logging** | No visibility into usage, errors, latency, or spend | [#21](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/21) |
| 5 | **Document updates require an image rebuild** | Non-technical staff can't update club docs themselves | [#20](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/20) |
| 6 | **Feedback stored in a container-local JSON file** | Lost on restart, same ephemerality problem as sessions | [#17](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/17) |
| 7 | **No OCR** | Scanned/image-only PDFs ingest as empty text (current docs are all text-based, so not yet a problem) | [#30](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/30) |
| 8 | **No streaming** | Answers appear all at once after ~2–5s | [#15](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/15) |
| 9 | **Thin automated UI coverage** | Auth/chat flows tested manually + Playwright spike only | [#27](https://github.com/brentmid/LGAC-Virtual-Assistant/issues/27) |

---

## 4. Ownership decision (the club must choose)

The single most important transition decision is **who owns the accounts and the bill.** Three viable models — pick one before any technical work proceeds.

### Option A — Club takes over everything

The club creates its own Google Cloud project and Anthropic account, the code is redeployed there, and the developer steps away. Cleanest long-term; highest up-front lift for club IT.

- **Club provides:** a Google Cloud account with billing, an Anthropic API account with billing, a person who can run `gcloud` deploys.
- **Pros:** full control, no dependency on the original developer, billing is transparent and in the club's name.
- **Cons:** requires technical staff/vendor capable of operating Cloud Run; club owns all maintenance.
- **Best when:** the club has IT staff or a standing vendor relationship.

### Option B — Developer operates, club funds

The developer keeps running the system; the club supplies (or reimburses) the Anthropic API key and GCP costs. Transition is mostly billing + a support agreement, not a technical migration.

- **Club provides:** an Anthropic API key billed to the club, agreement on a monthly GCP reimbursement or a club-owned billing account linked to the existing project.
- **Pros:** minimal technical lift; fastest to "live for members."
- **Cons:** ongoing dependency on one person (bus-factor risk); needs a written support/availability expectation.
- **Best when:** the club has no IT capacity and wants to validate value before investing.

### Option C — Managed vendor / hosting partner

A third party (the original developer as a paid vendor, or an MSP) owns operations under a support contract.

- **Club provides:** a contract defining SLA, cost, and an exit/data-return clause.
- **Pros:** professional operations, defined accountability.
- **Cons:** recurring contract cost; still need a documented exit path so the club isn't locked in.
- **Best when:** the club wants reliability without building internal capability.

> **Recommendation to surface, not decide:** if a member-facing launch is near, start with **B** (fast, low-risk, proves value), with a written commitment to migrate to **A** or **C** once usage and cost are understood. Whatever the choice, the account-transfer mechanics below must be completed.

### Account-transfer checklist (applies to A and C)

- [ ] Club creates a Google Cloud organization/project under a club-owned Google account (Workspace recommended).
- [ ] Club creates an Anthropic account at console.anthropic.com and generates its own API key with a spend limit.
- [ ] Rotate **all three** secrets into the new project's Secret Manager (`anthropic-api-key`, `app-password`, `admin-password`) — do not reuse the developer's key.
- [ ] Redeploy per `DEPLOYMENT_PLAN.md` against the club's project (the runbook is project-portable; only the project ID and account change).
- [ ] Re-point any custom domain / DNS (Section 6) at the new service.
- [ ] Set an Anthropic monthly spend cap and a GCP budget alert.
- [ ] Transfer the GitHub repository (or fork it) to a club-owned org; remove the original developer's access if a clean break is intended.
- [ ] Confirm the developer's personal project can be safely deleted (no shared resources) and decommission it.

---

## 5. Path to production — phased roadmap

Each phase is independently shippable. Effort estimates are rough developer-days for someone familiar with the stack. Tackle in order; phases 1–3 are the genuine blockers for opening to the full membership.

### Phase 0 — Account transfer & baseline ops *(prerequisite)*
Complete Section 4's transfer checklist. Add a GCP budget alert and an Anthropic spend cap. **~1–2 days.**

### Phase 1 — Real authentication *(issue #16)*
Replace the shared password with per-member identity. Options, cheapest to richest:
- **Magic-link / email OTP** against a member email list — light, no password management.
- **OAuth / SSO** if the club has Google Workspace or a member portal that can act as an identity provider.
- **Integration with the club's existing member-management system** (e.g., Jonas, ClubEssential, MembersFirst) if one exists — ideal, since it reuses the real member roster.
`sessions.py` and the `/api/auth` flow are the integration points. **~3–8 days** depending on the chosen IdP.

### Phase 2 — Persistent sessions & feedback *(issue #17)*
Move sessions (and the feedback store) out of process memory into **Redis** (e.g., Memorystore) or a managed database (Cloud SQL / Firestore). This is what makes >1 instance and zero-downtime redeploys safe. Swap the in-memory dict in `sessions.py` and the JSON writes in `feedback.py` for the chosen backend. **~2–4 days.**

### Phase 3 — Rate limiting & abuse controls *(issue #18)*
Per-user and per-IP request caps to bound Anthropic spend, enforced in FastAPI middleware (backed by the same Redis from Phase 2) or at the edge (Cloud Armor). Add a global daily cap as a circuit breaker. **~1–3 days.**

### Phase 4 — Monitoring, logging & cost visibility *(issue #21)*
Structured request logs, dashboards for query volume / latency / error rate, and **Anthropic cost tracking**. Cloud Run integrates with Cloud Logging/Monitoring out of the box; add alerts for error spikes and budget thresholds. Log queries (with privacy review) during the testing phase to evaluate answer quality. **~2–4 days.**

### Phase 5 — Self-service document management *(issue #20)*
Today, updating a club document means rebuilding the Docker image. Add an authenticated admin endpoint to upload/replace documents and trigger re-indexing, so non-technical staff can keep content current. Requires moving the Chroma index off the read-only image into persistent storage. **~4–8 days.**

### Phase 6 — Quality & UX polish *(issues #15, #27, #30)*
Streaming responses (#15), broader automated browser tests (#27), and OCR for any future scanned/image documents (#30). Prompt tuning in `prompts.py` based on real feedback. **~3–6 days, ongoing.**

**Rough total to a defensible production system (Phases 0–4):** ~9–21 developer-days. Phases 5–6 are quality-of-life and can follow launch.

---

## 6. Operational reference

### Custom domain
Members will expect something friendlier than `*.run.app`. Map a club subdomain (e.g., `assistant.thelandings.com`) via **Cloud Run domain mapping** or a load balancer; Cloud Run provisions the TLS cert. Update DNS and the HSTS/redirect middleware tolerates the new host automatically.

### Updating club documents (current process)
1. Place new/updated files in `rag-docs/` locally (the directory is gitignored — keep an authoritative copy backed up; it is the only non-disposable data).
2. Run `python scripts/ingest_docs.py` to verify ingestion and chunk counts.
3. Rebuild and redeploy per `DEPLOYMENT_PLAN.md` "Subsequent Deploys."
Phase 5 replaces this with a self-service admin flow.

### Backup & disaster recovery
- **The only irreplaceable data is `rag-docs/`** — the source documents. Everything else (Chroma index, container image) is rebuildable from them. Back up `rag-docs/` outside the container.
- Once sessions/feedback move to a database (Phase 2), add that database to the backup scope.
- Recovery = redeploy from the repo + `rag-docs/`. The runbook is `DEPLOYMENT_PLAN.md`.

### Secrets & key rotation
All secrets live in Secret Manager. Rotate the Anthropic key if it is ever exposed; update the secret version and redeploy. Never commit `.env` or keys (already gitignored).

### Cost monitoring
- **GCP**: budget alert on the project.
- **Anthropic**: hard monthly spend cap + usage alerts at console.anthropic.com. At ~$0.01–0.03/query, 1,000 queries/month ≈ $10–30/month in API cost; Cloud Run idle cost is ~$0.

### Model upgrades
The Claude model is set via the `CLAUDE_MODEL` env var (currently `claude-sonnet-4-6`). Newer models can be adopted by changing that variable and redeploying; re-run the QA checklist after any model change.

---

## 7. Recommended sequence

1. **Decide ownership** (Section 4) — nothing else can proceed cleanly until this is settled.
2. **Phase 0** — transfer accounts, set spend caps. The system is now club-owned.
3. **Phases 1–3** — auth, persistent sessions, rate limiting. These are the gate to opening for the full membership.
4. **Soft launch** to a member subset behind the new auth; turn on monitoring (Phase 4) and watch cost/quality.
5. **Phase 5–6** — self-service docs and UX polish once it's proven in members' hands.

---

## 8. Open questions for the club

- Does the club have an existing member-management / identity system the assistant should authenticate against? (Drives Phase 1.)
- Who will own day-to-day operations — internal IT, the original developer, or a vendor? (Section 4.)
- What is the acceptable monthly budget ceiling for API + hosting? (Sets the rate-limit and spend-cap configuration.)
- Is logging member queries for quality review acceptable under the club's privacy expectations? (Affects Phase 4.)
- What subdomain should the service live at? (Section 6.)
