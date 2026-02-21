from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    password: str


class AuthResponse(BaseModel):
    session_id: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class SourceInfo(BaseModel):
    document: str
    excerpt: str = ""


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = Field(default_factory=list)


class DocumentChunk(BaseModel):
    text: str
    metadata: dict = Field(default_factory=dict)

    @property
    def source_name(self) -> str:
        return self.metadata.get("source", "Unknown")

    @property
    def chunk_index(self) -> int:
        return self.metadata.get("chunk_index", 0)


class HealthResponse(BaseModel):
    status: str = "ok"
    documents_indexed: int = 0
