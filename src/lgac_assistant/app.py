import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .models import AuthRequest, AuthResponse, ChatRequest, ChatResponse, HealthResponse
from .rag import RAGEngine
from .sessions import SessionManager
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(title="LGAC Virtual Assistant", version="0.1.0")

# Initialize components
vector_store = VectorStore(settings.chroma_persist_dir)
session_manager = SessionManager(expiry_minutes=settings.session_expiry_minutes)
rag_engine = RAGEngine(
    vector_store=vector_store,
    model=settings.claude_model,
    api_key=settings.anthropic_api_key,
)


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


@app.get("/")
async def index():
    return FileResponse("static/index.html")


# Mount static files last so API routes take precedence
app.mount("/static", StaticFiles(directory="static"), name="static")
