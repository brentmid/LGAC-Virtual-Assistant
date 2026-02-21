from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    app_password: str = "changeme"
    claude_model: str = "claude-sonnet-4-0"
    host: str = "0.0.0.0"
    port: int = 9247
    chroma_persist_dir: str = "./chroma_data"
    rag_docs_dir: str = "./rag-docs"
    session_expiry_minutes: int = 30
    rag_top_k: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 100

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_persist_dir)

    @property
    def docs_path(self) -> Path:
        return Path(self.rag_docs_dir)


def get_settings() -> Settings:
    return Settings()
