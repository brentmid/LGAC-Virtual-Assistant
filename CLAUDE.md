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
| PDF extraction | PyMuPDF + pdfplumber fallback | PyMuPDF is fast for text-heavy PDFs; pdfplumber handles tables and complex layouts |
| DOCX extraction | python-docx | Standard, reliable Word document parsing |
| Frontend | Vanilla HTML/CSS/JS | No build step, no framework overhead for a single-page chat UI |
| Container | Docker | Standard containerization for reproducible deployment |
| Deployment | Google Cloud Run | HTTPS out of the box, scale-to-zero (no cost when idle), simple deploy |

## Project Structure

```
src/lgac_assistant/     # Python package
  config.py             # Pydantic settings from .env
  models.py             # Data models (ChatRequest, ChatResponse, etc.)
  ingest.py             # PDF/DOCX extraction + chunking
  vectorstore.py        # ChromaDB wrapper
  rag.py                # Retrieval + Claude API call
  prompts.py            # System prompt, RAG template, guardrails
  sessions.py           # In-memory session manager with expiry
  app.py                # FastAPI routes + static files
  __main__.py           # Uvicorn entry point
static/                 # Frontend (index.html, style.css, app.js)
scripts/ingest_docs.py  # CLI to build vector index
tests/                  # Test suite (29 tests)
rag-docs/               # Club documents (gitignored — not in repo)
chroma_data/            # Persisted vector index (gitignored — built from docs)
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

6. **PyMuPDF with pdfplumber fallback** — PyMuPDF is tried first (fast, handles most PDFs well). If it yields fewer than 100 characters of text (indicating a scanned/image-heavy PDF), pdfplumber is used instead (slower but handles tables and complex layouts better).

7. **Character-based chunking with boundary awareness** — Chunks target ~800 tokens (~3200 characters) with 100-token overlap. The chunker tries to split at paragraph boundaries first, then sentence boundaries, to avoid breaking mid-thought. This is a pragmatic approach; section-aware chunking would be better but requires document-specific parsing.

8. **No streaming** — The MVP returns complete responses rather than streaming tokens. This simplifies the implementation. Streaming can be added later for better perceived performance.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/auth` | Validate password, return `session_id` |
| `POST` | `/api/chat` | Send message, get RAG response + source citations |
| `GET` | `/api/health` | Health check — returns status and indexed document count |
| `GET` | `/` | Serve the frontend chat interface |

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

## RAG Pipeline

1. **Offline ingestion** (`scripts/ingest_docs.py`):
   - Scan `rag-docs/` for PDF and DOCX files
   - Extract text (PyMuPDF → pdfplumber fallback for PDFs; python-docx for DOCX)
   - Chunk text (~800 tokens per chunk, 100-token overlap, paragraph-boundary-aware)
   - Embed chunks using `all-MiniLM-L6-v2` and store in ChromaDB

2. **Query time** (`rag.py`):
   - Embed the user's question
   - Retrieve top-5 most similar chunks from ChromaDB
   - Build prompt: system prompt + retrieved context + conversation history + question
   - Call Claude Sonnet 4 API
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

## Deployment

1. **Local dev**: `pip install -e ".[dev]"` → `python scripts/ingest_docs.py` → `python -m lgac_assistant` → http://localhost:9247
2. **Local container**: `docker-compose up --build` → http://localhost:9247
3. **Cloud Run**: Build image → push to GCR → deploy with env vars → HTTPS URL for testers

Cloud Run config: 1 CPU, 1GB RAM, scale 0-2 instances, `--allow-unauthenticated` (the app handles auth internally via the shared password).

## Current Stats (MVP)

- 13 source documents (11 PDF, 2 DOCX)
- 194 chunks indexed in ChromaDB
- 29 tests passing
- Expected cost per query: ~$0.01-0.03 (Claude Sonnet 4 pricing)

## Known Limitations (MVP)

- **No OCR**: Scanned/image-only PDFs will produce empty or minimal text. The current documents are all text-based PDFs, so this isn't an issue yet.
- **No streaming**: Responses are returned all at once. Long answers may feel slow (~2-5 seconds).
- **Session loss on restart**: In-memory sessions are lost when the container restarts.
- **Single password**: All testers share one password. No per-user accounts.
- **No rate limiting**: A user could send unlimited requests. Cloud Run's max-instances cap provides some protection.
- **No HTTPS in local dev**: Only HTTPS when deployed to Cloud Run.
- **Chunking is approximate**: Token counts are estimated via character count (~4 chars/token). Not exact.
- **No section-aware parsing**: Chunks may split across document sections. Works well enough for the current documents.

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

**Status as of 2026-02-21**: MVP code is complete. All 29 tests pass. 194 chunks indexed from 13 documents. `.env` is configured with a live Anthropic API key using Claude Sonnet 4.6. Server port changed to 9247 to avoid conflicts. Auth screen and chat layout CSS bugs fixed. Manual QA in progress — needs to be completed.

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
- Expected: maintains conversation context, answers about dining dress code
- **Known issue**: dining dress code answers may be incomplete due to garbled PDF table extraction (#31). The dress code grid PDF has rotated column headers that extract backwards. If the answer says it can't find dining info, that's the known bug, not a model failure.

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

#### Test 8: Markdown Rendering (known issue)
- During any of the above tests, observe if responses contain raw markdown (`**bold**`, `- bullets`, etc.)
- **Known issue**: markdown is not rendered as HTML (#28)

### After QA Passes

1. **Fix dress code table extraction** (#31, high priority) — dining dress code questions fail due to garbled PDF parsing
2. **Deploy to Cloud Run** (#19) — gets an HTTPS URL to share with testers
3. **Add feedback mechanism** (#32) — let testers report issues inline
4. **Render markdown in responses** (#28) — improve readability
5. **Tune prompt** — adjust `src/lgac_assistant/prompts.py` based on answer quality observations

### Open GitHub Issues

| # | Title | Priority | Category |
|---|-------|----------|----------|
| 31 | Fix table extraction for dress code grid PDF | High | Bug |
| 29 | Improve document parsing pipeline for complex layouts | High | Enhancement |
| 32 | Add user feedback collection and admin review page | Medium | Feature |
| 28 | Render markdown in assistant responses as HTML | Medium | Enhancement |
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

### Completed This Session (2026-02-21)

- Changed default port from 8000 to 9247 (#22, PR #23)
- Fixed auth screen not hiding after login (#25, PR #26)
- Fixed chat input layout — full-width spanning (#25, PR #33)
- Upgraded LLM from Claude Sonnet 4 to Sonnet 4.6
- Verified Playwright MCP browser testing works (basis for #27)
- Created issues #24, #27, #28, #29, #30, #31, #32
