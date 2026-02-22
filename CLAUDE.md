# CLAUDE.md

## Project Overview

LGAC Virtual Assistant — A RAG-powered Q&A chatbot for Landings Golf & Athletic Club (LGAC) members. Members can ask questions about club policies, operations, dress codes, rules, membership, amenities, and more. The assistant answers only from provided club documents (13 PDFs and DOCX files).

This is an MVP proof-of-concept intended to get in front of testers quickly, then iterate.

**Repository**: `github.com:brentmid/LGAC-Virtual-Assistant` (private)

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Best RAG library ecosystem |
| Web framework | FastAPI + Uvicorn | Async, fast, minimal boilerplate |
| LLM | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | Best cost/quality balance for document Q&A; upgraded from Sonnet 4 on 2026-02-21 |
| Vector store | ChromaDB (embedded) | No separate database service needed; persists to disk; good enough for <1000 chunks |
| Embeddings | `all-MiniLM-L6-v2` (ChromaDB default) | Free, runs locally, no extra API key; adequate for semantic search at this scale |
| PDF extraction | PyMuPDF + pdfplumber fallback | PyMuPDF is fast for text-heavy PDFs; pdfplumber handles tables, complex layouts, and rotated text |
| DOCX extraction | python-docx | Standard, reliable Word document parsing |
| Markdown rendering | marked.js + DOMPurify (CDN) | Renders assistant markdown as HTML; DOMPurify sanitizes for XSS |
| Frontend | Vanilla HTML/CSS/JS | No build step, no framework overhead for a single-page chat UI |
| Container | Docker | Standard containerization for reproducible deployment |
| Deployment | Google Cloud Run | HTTPS out of the box, scale-to-zero (no cost when idle), simple deploy |

## Project Structure

```
src/lgac_assistant/     # Python package
  config.py             # Pydantic settings from .env
  models.py             # Data models (ChatRequest, ChatResponse, Feedback*, etc.)
  ingest.py             # PDF/DOCX extraction + chunking
  vectorstore.py        # ChromaDB wrapper
  rag.py                # Retrieval + Claude API call
  prompts.py            # System prompt, RAG template, guardrails
  sessions.py           # In-memory session manager with expiry
  feedback.py           # JSON file-based feedback storage
  app.py                # FastAPI routes + static files
  __main__.py           # Uvicorn entry point
static/                 # Frontend (index.html, style.css, app.js, admin.html)
scripts/ingest_docs.py  # CLI to build vector index
tests/                  # Test suite (51 tests)
rag-docs/               # Club documents (gitignored — not in repo)
chroma_data/            # Persisted vector index (gitignored — built from docs)
feedback.json           # Feedback records (gitignored — created at runtime)
```

## Common Commands

```bash
# Install for development
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Build vector index from documents
python scripts/ingest_docs.py

# Run the server
python -m lgac_assistant

# Run tests
pytest

# Lint
ruff check src/ tests/
```

## Key Design Decisions

1. **ChromaDB index baked into Docker image** — Club documents are static and change infrequently. The vector index is built at `docker build` time via `scripts/ingest_docs.py`. No runtime ingestion needed. When docs change, rebuild the image. This avoids the complexity of a separate database service and ensures the deployed container is fully self-contained.

2. **Conversation history in RAG prompt** — Session history is included in the prompt text alongside retrieved context (not as separate API message turns). This keeps the API call to a single user message and ensures the context documents are always adjacent to the question, which produces better answers.

3. **Club-topics-only guardrails** — The system prompt (`prompts.py`) instructs Claude to politely decline off-topic questions and only answer based on provided context. It never fabricates information — if the context doesn't contain an answer, it says so and suggests contacting the club directly.

4. **Shared password auth (MVP only)** — Simple password gate for the testing phase. Password is set via `APP_PASSWORD` environment variable. On successful auth, a UUID session ID is returned and stored in the browser's JS runtime (lost on page refresh — acceptable for MVP). This is NOT production-grade auth; see "Production Considerations" below.

5. **Session state in memory** — A Python dict maps `session_id` → conversation history. Sessions expire after 30 minutes of inactivity. All sessions are lost on container restart. This is acceptable for MVP but would need Redis or a database for production.

6. **PyMuPDF with pdfplumber fallback** — PyMuPDF is tried first (fast, handles most PDFs well). Falls back to pdfplumber if PyMuPDF yields fewer than 100 characters, produces reversed text (from rotated column headers), or outputs orphaned grid data (standalone Y/N lines without column context). pdfplumber's table extractor detects reversed headers, fixes them, and formats tables as structured `Item | Venue: Value` output for better RAG retrieval. Layout-artifact tables (empty headers, single column, >80% empty cells) are filtered out. Normal tables are formatted with header context (`Header: Value | ...`) instead of raw cell dumps.

7. **Section-aware chunking with boundary detection** — Chunks target ~800 tokens (~3200 characters) with 100-token overlap. The chunker tries to split at section headings first, then paragraph boundaries, then sentence boundaries. ALL-CAPS section headings are detected and prepended in `[BRACKETS]` to chunks that don't naturally start with their heading. Section names are stored in chunk metadata for retrieval context.

8. **DOCX table extraction** — `extract_docx()` iterates document body children in order (paragraphs and tables interleaved) rather than reading only paragraphs. Tables are formatted as `Header: Value | ...` with merged-cell deduplication.

9. **Repeated header/footer removal** — After text extraction, lines appearing more than 3 times (≥10 chars) are removed except for the first occurrence. Duplicate decorative dividers are also collapsed. This prevents headers like "RULES & REGULATIONS" (43 occurrences) from polluting chunk content and retrieval.

10. **No streaming** — The MVP returns complete responses rather than streaming tokens. This simplifies the implementation. Streaming can be added later for better perceived performance.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth` | Validate password, return `session_id` |
| `POST` | `/api/chat` | Send message, get RAG response + source citations |
| `POST` | `/api/feedback` | Submit feedback on the last Q&A pair |
| `POST` | `/api/admin/auth` | Admin login, return admin `session_id` |
| `GET` | `/api/admin/feedback` | Retrieve all feedback records (admin auth required) |
| `GET` | `/api/health` | Health check — returns status and indexed document count |
| `GET` | `/` | Serve the frontend chat interface |
| `GET` | `/admin` | Serve the admin feedback review page |

### Request/Response Examples

**Auth:**
```json
// POST /api/auth
{"password": "the-shared-password"}
// → 200: {"session_id": "uuid-here"}
// → 401: {"detail": "Invalid password"}
```

**Chat:**
```json
// POST /api/chat
{"session_id": "uuid-here", "message": "What is the dress code for golf?"}
// → 200: {"answer": "...", "sources": [{"document": "TLGACDressCodeGRID2026.pdf", "excerpt": "..."}]}
// → 401: {"detail": "Invalid or expired session"}
```

**Feedback:**
```json
// POST /api/feedback
{"session_id": "uuid-here", "feedback": "Great answer, very helpful!"}
// → 200: {"message": "Thank you for your feedback!"}
// → 401: {"detail": "Invalid or expired session"}
```

**Admin:**
```json
// POST /api/admin/auth
{"password": "admin-password"}
// → 200: {"session_id": "admin-uuid"}
// → 401: {"detail": "Invalid password"}
// → 403: {"detail": "Admin access is disabled"}

// GET /api/admin/feedback (header: X-Admin-Session: admin-uuid)
// → 200: [{"timestamp": "...", "question": "...", "response": "...", "feedback": "...", "session_id": "..."}]
// → 401: {"detail": "Admin authentication required"}
```

## RAG Pipeline

1. **Offline ingestion** (`scripts/ingest_docs.py`):
   - Scan `rag-docs/` for PDF and DOCX files
   - Extract text (PyMuPDF → pdfplumber fallback for PDFs; python-docx with table support for DOCX)
   - Remove repeated headers/footers (lines appearing >3 times)
   - Filter layout-artifact tables; format real tables as `Header: Value | ...`
   - Chunk text (~800 tokens per chunk, 100-token overlap, section/paragraph/sentence-boundary-aware)
   - Prepend section headings to chunks that don't naturally contain them
   - Embed chunks using `all-MiniLM-L6-v2` and store in ChromaDB
   - Print `IngestionMetrics` summary (documents, chunks, headers removed, sections detected, etc.)

2. **Query time** (`rag.py`):
   - Embed the user's question
   - Retrieve top-5 most similar chunks from ChromaDB
   - Build prompt: system prompt + retrieved context + conversation history + question
   - Call Claude Sonnet 4.6 API
   - Return answer text + deduplicated source document citations

## Environment Variables

See `.env.example` for all settings. **Required**: `ANTHROPIC_API_KEY`, `APP_PASSWORD`.

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(required)* | Anthropic API key from console.anthropic.com |
| `APP_PASSWORD` | `changeme` | Shared password for the testing phase |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model ID (see Anthropic docs for options) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `9247` | Server port |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | Path where ChromaDB stores its index |
| `RAG_DOCS_DIR` | `./rag-docs` | Path to source documents |
| `SESSION_EXPIRY_MINUTES` | `30` | Session timeout (minutes of inactivity) |
| `RAG_TOP_K` | `5` | Number of document chunks to retrieve per query |
| `CHUNK_SIZE` | `800` | Target chunk size in approximate tokens |
| `CHUNK_OVERLAP` | `100` | Overlap between consecutive chunks in approximate tokens |
| `ADMIN_PASSWORD` | *(empty — disabled)* | Password for the admin feedback review page |
| `FEEDBACK_FILE` | `./feedback.json` | Path to the feedback storage file |

## Deployment

1. **Local dev**: `pip install -e ".[dev]"` → `python scripts/ingest_docs.py` → `python -m lgac_assistant` → http://localhost:9247
2. **Local container**: `docker-compose up --build` → http://localhost:9247
3. **Cloud Run**: Build image → push to GCR → deploy with env vars → HTTPS URL for testers

Cloud Run config: 1 CPU, 1GB RAM, scale 0-2 instances, `--allow-unauthenticated` (the app handles auth internally via the shared password).

## Current Stats (MVP)

- 13 source documents (11 PDF, 2 DOCX)
- 205 chunks indexed in ChromaDB
- 66 tests passing
- Expected cost per query: ~$0.01-0.03 (Claude Sonnet 4.6 pricing)

## Known Limitations (MVP)

- **No OCR**: Scanned/image-only PDFs will produce empty or minimal text. The current documents are all text-based PDFs, so this isn't an issue yet.
- **No streaming**: Responses are returned all at once. Long answers may feel slow (~2-5 seconds).
- **Session loss on restart**: In-memory sessions are lost when the container restarts.
- **Single password**: All testers share one password. No per-user accounts.
- **No rate limiting**: A user could send unlimited requests. Cloud Run's max-instances cap provides some protection.
- **No HTTPS in local dev**: Only HTTPS when deployed to Cloud Run.
- **Chunking is approximate**: Token counts are estimated via character count (~4 chars/token). Not exact.

## Production Considerations

For club IT staff planning a production deployment:

1. **Authentication**: Replace the shared password with proper member auth (OAuth, SSO, or integration with the club's member portal). The `sessions.py` module would need to be replaced.
2. **Session storage**: Move from in-memory dict to Redis or a database so sessions survive restarts and work across multiple instances.
3. **Rate limiting**: Add per-user rate limiting (e.g., via FastAPI middleware or Cloud Run quotas) to control API costs.
4. **HTTPS**: Cloud Run provides this automatically. For other deployments, put a reverse proxy (nginx, Caddy) in front.
5. **Monitoring**: Add logging/metrics for query volume, response latency, error rates, and API costs. Consider Anthropic's usage dashboard.
6. **Document updates**: Currently requires rebuilding the Docker image. A future version could add an admin endpoint for document upload and re-indexing.
7. **Cost management**: Set up Anthropic API usage alerts. At ~$0.01-0.03/query, 1000 queries/month ≈ $10-30/month in API costs.
8. **Backup**: The ChromaDB index is disposable (rebuilt from source docs). Back up the source documents in `rag-docs/`.
9. **Content moderation**: The system prompt prevents off-topic answers, but consider logging queries for review during the testing phase.

## Current Status & Next Steps

**Status as of 2026-02-22**: MVP code is complete with feedback collection and improved document parsing pipeline. All 66 tests pass. 205 chunks indexed from 13 documents. `.env` is configured with a live Anthropic API key using Claude Sonnet 4.6. Server port changed to 9247 to avoid conflicts. Testers can submit feedback on answers by typing `feedback:` followed by comments. Admin review page at `/admin` (requires `ADMIN_PASSWORD` env var). Ready for Cloud Run deployment.

### Resume Development

```bash
cd ~/bin/LGAC-Virtual-Assistant
source .venv/bin/activate
python -m lgac_assistant
# Server runs at http://localhost:9247
# Password: lgac2026
```

If port 9247 is already in use: `lsof -ti:9247 | xargs kill`

**Important**: Use incognito/private windows for testing to avoid CSS caching issues. Cmd+Shift+N (Chrome) or Cmd+Shift+P (Safari).

### Manual QA Checklist (not yet completed)

Run through these tests with the server running at http://localhost:9247. Use a new incognito window for each test session to avoid cache issues.

#### Test 1: Password Gate
1. Open http://localhost:9247
2. Enter wrong password → should show "Invalid password"
3. Enter correct password (`lgac2026`) → should enter chat interface
4. Verify: auth screen disappears completely, chat input spans full browser width

**Status**: Auth screen fix verified via Playwright. Needs manual confirmation.

#### Test 2: Club Question
- Ask: **"What is the dress code for golf?"**
- Expected: relevant answer citing dress code documents
- Check: sources listed should include `TLGACDressCodeGRID2026.pdf`

#### Test 3: Follow-up with Context
- Ask (immediately after Test 2): **"What about dining?"**
- Expected: maintains conversation context, answers about dining dress code with venue-specific details (e.g., Palmer's Steakhouse vs. The Deck have different rules)

#### Test 4: Off-topic Question
- Ask: **"What's the weather today?"**
- Expected: politely declines, explains it only answers club-related questions

#### Test 5: Specific Policy
- Ask: **"What are the annual dues?"**
- Expected: cites the `DuesSheet26_11.1.25.pdf`
- Check: amounts and membership categories should be accurate to the document

#### Test 6: Vague Question
- Ask: **"Tell me about the club"**
- Expected: general overview drawn from brochure documents
- Check: sources should include `TLGAC_BrochureWEB.pdf` or `TLGAC_MbrshipOverview25_12.10.25.pdf`

#### Test 7: Unknown Topic
- Ask: **"What is the wifi password?"**
- Expected: admits it doesn't know, suggests contacting the club directly
- Check: should NOT fabricate an answer

#### Test 8: Feedback Submission
- Ask any club question first (e.g., "What is the dress code for golf?")
- Then type: **feedback: Great answer, very helpful!**
- Expected: feedback message shows as user message, confirmation "Thank you for your feedback!" shows as assistant message
- Check: message was NOT sent to Claude (no typing indicator, instant response)
- Check: visit `/admin`, authenticate with `ADMIN_PASSWORD`, verify the feedback appears in the table with the correct question and response

#### Test 9: Markdown Rendering
- During any of the above tests, verify that assistant responses render markdown properly
- Headings should appear as headings, bold text as bold, bullet lists as lists
- User messages should still display as plain text (no markdown rendering)

### After QA Passes

1. **Deploy to Cloud Run (#19 + #24)** — full plan documented in `DEPLOYMENT_PLAN.md`. Summary:
   - Brent creates a GCP project, enables billing, authenticates `gcloud` with Workspace account
   - Claude adds HTTPS redirect middleware (~20 lines in `app.py`) + HSTS header
   - Build image via Cloud Build (remote, avoids ARM64→amd64 cross-compile)
   - Secrets (API key, passwords) go in Google Secret Manager
   - Deploy to Cloud Run: 1 CPU, 1GB RAM, 0-2 instances, `--allow-unauthenticated`
   - Cloud Run provides automatic HTTPS on `*.run.app` domain (solves #24)
   - Estimated GCP cost: < $5/month for MVP tester traffic
   - Tools ready: `gcloud` v533.0.0 installed, `brew` available for anything else
2. **Tune prompt** — adjust `src/lgac_assistant/prompts.py` based on answer quality observations

### Open GitHub Issues

| # | Title | Priority | Category |
|---|-------|----------|----------|
| ~~29~~ | ~~Improve document parsing pipeline for complex layouts~~ | ~~High~~ | ~~Done~~ |
| 30 | Add OCR support for image-based documents | Medium | Enhancement |
| 27 | Add Playwright browser tests for auth flow and chat UI | Medium | Testing |
| 24 | Require HTTPS before cloud deployment | Medium | Infrastructure |
| 19 | Google Cloud Run deployment | Medium | Infrastructure |
| 21 | Monitoring and logging | Low | Feature |
| 20 | Admin document upload and re-indexing | Low | Feature |
| 18 | Rate limiting | Low | Security |
| 17 | Persistent session storage | Low | Feature |
| 16 | Production authentication (OAuth/SSO) | Low | Feature |
| 15 | Streaming responses | Low | Enhancement |

### Completed (2026-02-22)

- Improved document parsing pipeline (#29) — header/footer removal (92 lines cleaned across 6 docs), DOCX table extraction (Hours of Operations now 2 chunks instead of 1), layout table filtering, normal table formatting with header context, section-aware chunking with heading prepend and metadata; 15 new tests; vector index rebuilt: 203 → 205 chunks
- Added user feedback collection (#32) — testers type `feedback:` prefix in chat to submit feedback on the last Q&A pair; stored to `feedback.json`; admin review page at `/admin` with password auth; 13 new tests

### Completed (2026-02-21)

- Changed default port from 8000 to 9247 (#22, PR #23)
- Fixed auth screen not hiding after login (#25, PR #26)
- Fixed chat input layout — full-width spanning (#25, PR #33)
- Upgraded LLM from Claude Sonnet 4 to Sonnet 4.6 (PR #35)
- Fixed PDF table extraction for rotated/reversed column headers (#31, PR #36) — dress code grid now extracts with correct venue names; added reversed-text detection, quality-based PyMuPDF→pdfplumber fallthrough, and structured table formatting
- Rebuilt vector index: 194 → 203 chunks (improved extraction for 3 PDFs containing grid tables)
- Verified Playwright MCP browser testing works (basis for #27)
- Created issues #24, #27, #28, #29, #30, #31, #32
- Rendered markdown in assistant responses as HTML (#28) — added marked.js + DOMPurify via CDN; assistant messages render headings, lists, bold/italic, code blocks; user messages stay plain text; XSS-safe via DOMPurify sanitization
