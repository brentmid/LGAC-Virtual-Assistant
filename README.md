# LGAC Virtual Assistant

A RAG-powered virtual assistant for members of The Landings Golf & Athletic Club. Members can ask questions about club policies, operations, dress code, golf, dining, membership, rules, and more — the assistant answers only from official club documents.

## How It Works

The assistant uses **Retrieval-Augmented Generation (RAG)** to answer questions:

1. Club documents (PDFs and DOCX files) are pre-processed into searchable chunks stored in a vector database (ChromaDB)
2. When a member asks a question, the most relevant document sections are automatically retrieved
3. Those sections are sent to Claude (Anthropic's AI) along with the question and conversation history
4. Claude generates an answer based only on the provided context, citing source documents
5. If the documents don't contain relevant information, the assistant says so and suggests contacting the club directly

The assistant will politely decline to answer questions unrelated to the club.

## Quick Start

### Prerequisites

- Python 3.11 or later (tested with 3.13)
- An [Anthropic API key](https://console.anthropic.com/)
- Club documents (PDF and/or DOCX files)

### Setup

```bash
# Clone the repository
git clone git@github.com:brentmid/LGAC-Virtual-Assistant.git
cd LGAC-Virtual-Assistant

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY and APP_PASSWORD (see Configuration below)
```

### Add Club Documents

Place PDF and DOCX files in the `rag-docs/` directory. Supported formats:

- **PDF** (`.pdf`) — text-based PDFs work best; scanned/image-only PDFs are not supported (no OCR)
- **Word** (`.docx`) — standard Word documents

The current document set includes 13 files: golf handbooks, dress code grids, rules & regulations, bylaws, membership overviews, hours of operation, dues sheets, and brochures.

### Build the Search Index

```bash
python scripts/ingest_docs.py
```

This extracts text from all documents, splits it into chunks, and stores the embeddings in ChromaDB. The script reports how many chunks were created and runs a verification query.

### Run the Server

```bash
python -m lgac_assistant
```

Open http://localhost:9247, enter the shared password, and start asking questions.

## Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or use the rebuild script (stops, rebuilds from scratch, restarts)
./rebuild.sh
```

The Docker image builds the document index at image build time. The `rag-docs/` directory must contain the club documents before building. No runtime ingestion is needed — the container is fully self-contained.

## Google Cloud Run Deployment

### First-Time Setup

```bash
# Authenticate with Google Cloud
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable required APIs
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

### Deploy

```bash
# Build and push the image
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/lgac-assistant

# Deploy to Cloud Run
gcloud run deploy lgac-assistant \
  --image gcr.io/YOUR_PROJECT_ID/lgac-assistant \
  --platform managed \
  --region us-east1 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 2 \
  --allow-unauthenticated
```

### Set Environment Variables (Secrets)

Do **not** pass API keys on the command line. Use Google Cloud Secret Manager:

```bash
# Create secrets
echo -n "sk-ant-YOUR-KEY" | gcloud secrets create anthropic-api-key --data-file=-
echo -n "your-password" | gcloud secrets create app-password --data-file=-

# Grant Cloud Run access
gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding app-password \
  --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

# Deploy with secrets
gcloud run deploy lgac-assistant \
  --image gcr.io/YOUR_PROJECT_ID/lgac-assistant \
  --update-secrets="ANTHROPIC_API_KEY=anthropic-api-key:latest,APP_PASSWORD=app-password:latest"
```

Cloud Run provides HTTPS automatically. The app handles authentication internally via the shared password — `--allow-unauthenticated` lets anyone reach the login page.

## Updating Documents

When club documents change:

1. Replace or add files in `rag-docs/`
2. **Local dev**: Re-run `python scripts/ingest_docs.py`
3. **Docker**: Rebuild the image with `./rebuild.sh`
4. **Cloud Run**: Rebuild and redeploy (`gcloud builds submit` + `gcloud run deploy`)

## Configuration

All settings are configured via environment variables or a `.env` file. See `.env.example` for a template.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | API key from [console.anthropic.com](https://console.anthropic.com/) |
| `APP_PASSWORD` | Yes | `changeme` | Shared password for the testing phase |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-0` | Claude model ID |
| `HOST` | No | `0.0.0.0` | Server bind address |
| `PORT` | No | `9247` | Server port |
| `CHROMA_PERSIST_DIR` | No | `./chroma_data` | ChromaDB storage path |
| `RAG_DOCS_DIR` | No | `./rag-docs` | Source documents directory |
| `SESSION_EXPIRY_MINUTES` | No | `30` | Session timeout (minutes of inactivity) |
| `RAG_TOP_K` | No | `5` | Number of document chunks retrieved per query |
| `CHUNK_SIZE` | No | `800` | Target chunk size (approximate tokens) |
| `CHUNK_OVERLAP` | No | `100` | Overlap between chunks (approximate tokens) |

## Testing

```bash
pytest                    # Run all 29 tests
pytest -v                 # Verbose output
pytest --cov              # With coverage report
ruff check src/ tests/    # Lint
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth` | Authenticate with shared password → returns `session_id` |
| `POST` | `/api/chat` | Send a message → returns answer + source citations |
| `GET` | `/api/health` | Health check (returns status and indexed document count) |
| `GET` | `/` | Chat interface (HTML page) |

### Example: Authenticate

```bash
curl -X POST http://localhost:9247/api/auth \
  -H "Content-Type: application/json" \
  -d '{"password": "your-password"}'
# → {"session_id": "abc123-..."}
```

### Example: Ask a Question

```bash
curl -X POST http://localhost:9247/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id": "abc123-...", "message": "What is the dress code for golf?"}'
# → {"answer": "...", "sources": [{"document": "TLGACDressCodeGRID2026.pdf", "excerpt": "..."}]}
```

## Architecture

```
Member → Password Gate → Chat UI
                           ↓
                      FastAPI Backend
                           ↓
                    ┌──────┴──────┐
                    │  RAG Engine │
                    └──────┬──────┘
               ┌───────────┼───────────┐
               ↓           ↓           ↓
          ChromaDB    Claude API   Session
          (vectors)   (Sonnet 4)   Manager
```

- **ChromaDB** stores document chunk embeddings locally (no external database)
- **Claude API** generates answers from retrieved context (Anthropic cloud service)
- **Session Manager** tracks conversation history in memory (per-session, 30-min expiry)

## Cost Estimates

- **Anthropic API**: ~$0.01-0.03 per query (Claude Sonnet 4 pricing). At 1,000 queries/month ≈ $10-30/month.
- **Google Cloud Run**: Scale-to-zero means no cost when idle. With light testing traffic, expect < $5/month for compute.
- **ChromaDB embeddings**: Free (runs locally using the bundled `all-MiniLM-L6-v2` model).

## Known Limitations (MVP)

- **No OCR**: Scanned or image-only PDFs will not produce usable text
- **No streaming**: Responses return all at once (~2-5 second wait)
- **Sessions lost on restart**: Conversation history is in memory only
- **Single shared password**: All testers use the same password; no per-user accounts
- **No rate limiting**: Users can send unlimited requests (Cloud Run max-instances provides some protection)
- **No HTTPS in local dev**: HTTPS is only available via Cloud Run or a reverse proxy

## Security Notes

This MVP uses a shared password for simplicity during testing. For production deployment:

- Replace shared password auth with proper member authentication (OAuth, SSO, or club portal integration)
- Move session storage from in-memory to Redis or a database
- Add per-user rate limiting to control API costs
- Use Google Cloud Secret Manager for API keys (never pass secrets on the command line)
- Consider logging queries during the testing phase for content review
- The system prompt prevents off-topic answers, but this is not a security boundary

## Troubleshooting

**Server won't start**: Check that `.env` exists with a valid `ANTHROPIC_API_KEY`. Check that `chroma_data/` exists (run `python scripts/ingest_docs.py` first).

**"Invalid or expired session" error**: Sessions expire after 30 minutes of inactivity, or when the server restarts. Refresh the page and re-enter the password.

**Empty or poor answers**: The document may not contain relevant information, or the PDF text extraction may have failed for that document. Check the ingestion log output for warnings. PDFs with mostly images/scans will not extract well.

**Docker build fails**: Ensure `rag-docs/` contains the club documents before building. The index is built during `docker build`.

## License

Private — The Landings Golf & Athletic Club.
