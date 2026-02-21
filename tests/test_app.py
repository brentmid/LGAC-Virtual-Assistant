import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["APP_PASSWORD"] = "testpass"


@pytest.fixture
def client():
    from lgac_assistant.app import app

    return TestClient(app)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "documents_indexed" in data


def test_auth_success(client):
    response = client.post("/api/auth", json={"password": "testpass"})
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert len(data["session_id"]) > 0


def test_auth_failure(client):
    response = client.post("/api/auth", json={"password": "wrongpassword"})
    assert response.status_code == 401


def test_chat_invalid_session(client):
    response = client.post(
        "/api/chat",
        json={"session_id": "invalid-id", "message": "Hello"},
    )
    assert response.status_code == 401


def test_chat_requires_auth(client):
    # First authenticate
    auth_response = client.post("/api/auth", json={"password": "testpass"})
    session_id = auth_response.json()["session_id"]

    # Mock the RAG engine to avoid calling Claude API
    from lgac_assistant import app as app_module
    from lgac_assistant.models import ChatResponse, SourceInfo

    mock_response = ChatResponse(
        answer="The dress code requires collared shirts.",
        sources=[SourceInfo(document="dresscode.pdf", excerpt="Collared shirts required")],
    )

    with patch.object(app_module.rag_engine, "query", return_value=mock_response):
        response = client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "What is the dress code?"},
        )

    assert response.status_code == 200
    data = response.json()
    assert "dress code" in data["answer"].lower() or "collared" in data["answer"].lower()
    assert len(data["sources"]) > 0


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "LGAC Virtual Assistant" in response.text
