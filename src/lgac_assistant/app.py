import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .feedback import FeedbackStore
from .models import (
    AuthRequest,
    AuthResponse,
    ChatRequest,
    ChatResponse,
    FeedbackRecord,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
)
from .rag import RAGEngine
from .sessions import SessionManager
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="LGAC Virtual Assistant", version="0.1.0")

# Initialize components
vector_store = VectorStore(settings.chroma_persist_dir)
session_manager = SessionManager(expiry_minutes=settings.session_expiry_minutes)
admin_session_manager = SessionManager(expiry_minutes=settings.session_expiry_minutes)
rag_engine = RAGEngine(
    vector_store=vector_store,
    model=settings.claude_model,
    api_key=settings.anthropic_api_key,
)
feedback_store = FeedbackStore(settings.feedback_file)


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        documents_indexed=vector_store.count(),
    )


@app.post("/api/auth", response_model=AuthResponse)
async def authenticate(request: AuthRequest):
    if request.password != settings.app_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    session = session_manager.create_session()
    return AuthResponse(session_id=session.id)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Add user message to history
    session.add_message("user", request.message)

    # Get RAG response with conversation history (exclude current message)
    response = rag_engine.query(
        question=request.message,
        history=session.history[:-1] if len(session.history) > 1 else None,
        top_k=settings.rag_top_k,
    )

    # Add assistant response to history
    session.add_message("assistant", response.answer)

    return response


@app.post("/api/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    # Find the last Q&A pair from session history
    question = ""
    response = ""
    for msg in reversed(session.history):
        if msg["role"] == "assistant" and not response:
            response = msg["content"]
        elif msg["role"] == "user" and not question:
            question = msg["content"]
        if question and response:
            break

    record = FeedbackRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        question=question,
        response=response,
        feedback=request.feedback,
        session_id=request.session_id,
    )
    feedback_store.add(record)
    return FeedbackResponse(message="Thank you for your feedback!")


@app.post("/api/admin/auth", response_model=AuthResponse)
async def admin_authenticate(request: AuthRequest):
    if not settings.admin_password:
        raise HTTPException(status_code=403, detail="Admin access is disabled")
    if request.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")
    session = admin_session_manager.create_session()
    return AuthResponse(session_id=session.id)


@app.get("/api/admin/feedback")
async def get_feedback(request: Request):
    session_id = request.headers.get("X-Admin-Session")
    if not session_id or not admin_session_manager.get_session(session_id):
        raise HTTPException(status_code=401, detail="Admin authentication required")
    records = feedback_store.get_all()
    return [r.model_dump() for r in records]


@app.get("/admin")
async def admin_page():
    return FileResponse("static/admin.html")


@app.get("/")
async def index():
    return FileResponse("static/index.html")


# Mount static files last so API routes take precedence
app.mount("/static", StaticFiles(directory="static"), name="static")
