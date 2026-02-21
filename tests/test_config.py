import os

from lgac_assistant.config import Settings


def test_default_settings():
    settings = Settings(anthropic_api_key="test-key")
    assert settings.port == 9247
    assert settings.session_expiry_minutes == 30
    assert settings.rag_top_k == 5
    assert settings.chunk_size == 800
    assert settings.chunk_overlap == 100


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.setenv("PORT", "9000")
    settings = Settings()
    assert settings.anthropic_api_key == "sk-test"
    assert settings.app_password == "secret"
    assert settings.port == 9000


def test_chroma_path():
    settings = Settings(anthropic_api_key="test", chroma_persist_dir="/tmp/chroma")
    assert str(settings.chroma_path) == "/tmp/chroma"


def test_docs_path():
    settings = Settings(anthropic_api_key="test", rag_docs_dir="/tmp/docs")
    assert str(settings.docs_path) == "/tmp/docs"
