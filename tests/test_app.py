import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["APP_PASSWORD"] = "testpass"
os.environ["ADMIN_PASSWORD"] = "adminpass"


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


def test_feedback_valid_session(client):
    # Authenticate and send a chat message first
    auth_response = client.post("/api/auth", json={"password": "testpass"})
    session_id = auth_response.json()["session_id"]

    from lgac_assistant import app as app_module
    from lgac_assistant.models import ChatResponse, SourceInfo

    mock_response = ChatResponse(
        answer="Collared shirts are required.",
        sources=[SourceInfo(document="dresscode.pdf", excerpt="Collared shirts")],
    )

    with patch.object(app_module.rag_engine, "query", return_value=mock_response):
        client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "What is the dress code?"},
        )

    # Now submit feedback
    response = client.post(
        "/api/feedback",
        json={"session_id": session_id, "feedback": "Great answer!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "thank you" in data["message"].lower()


def test_feedback_invalid_session(client):
    response = client.post(
        "/api/feedback",
        json={"session_id": "invalid-id", "feedback": "Test"},
    )
    assert response.status_code == 401


def test_feedback_stores_last_qa(client):
    auth_response = client.post("/api/auth", json={"password": "testpass"})
    session_id = auth_response.json()["session_id"]

    from lgac_assistant import app as app_module
    from lgac_assistant.models import ChatResponse, SourceInfo

    mock_response = ChatResponse(
        answer="Pool hours are 9am to 8pm.",
        sources=[SourceInfo(document="amenities.pdf", excerpt="Pool hours")],
    )

    with patch.object(app_module.rag_engine, "query", return_value=mock_response):
        client.post(
            "/api/chat",
            json={"session_id": session_id, "message": "What are pool hours?"},
        )

    # Submit feedback and verify it captured the Q&A
    client.post(
        "/api/feedback",
        json={"session_id": session_id, "feedback": "Helpful"},
    )

    records = app_module.feedback_store.get_all()
    # Find the record for this session
    matching = [r for r in records if r.session_id == session_id]
    assert len(matching) >= 1
    record = matching[0]
    assert record.question == "What are pool hours?"
    assert record.response == "Pool hours are 9am to 8pm."
    assert record.feedback == "Helpful"


def test_admin_auth_failure(client):
    response = client.post(
        "/api/admin/auth", json={"password": "wrongpassword"}
    )
    assert response.status_code == 401


def test_admin_feedback_without_auth(client):
    response = client.get("/api/admin/feedback")
    assert response.status_code == 401


def test_admin_auth_and_feedback_retrieval(client):
    # Authenticate as admin
    auth_response = client.post(
        "/api/admin/auth", json={"password": "adminpass"}
    )
    assert auth_response.status_code == 200
    admin_session_id = auth_response.json()["session_id"]

    # Retrieve feedback
    response = client.get(
        "/api/admin/feedback",
        headers={"X-Admin-Session": admin_session_id},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_admin_page(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Feedback Review" in response.text


# --- HTTPS redirect middleware tests ---


def test_https_redirect_when_forwarded_proto_http(client):
    """Cloud Run sends X-Forwarded-Proto: http — should 301 redirect to HTTPS."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "http",
            "Host": "lgac-assistant-abc123-uc.a.run.app",
        },
        follow_redirects=False,
    )
    assert response.status_code == 301
    assert response.headers["location"].startswith("https://")


def test_no_redirect_for_localhost(client):
    """Local dev should not redirect even with X-Forwarded-Proto: http."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "http",
            "Host": "localhost:9247",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_no_redirect_for_127_0_0_1(client):
    """127.0.0.1 should not redirect."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "http",
            "Host": "127.0.0.1:9247",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_no_redirect_when_already_https(client):
    """No redirect when X-Forwarded-Proto is already https."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "https",
            "Host": "lgac-assistant-abc123-uc.a.run.app",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_hsts_header_on_https(client):
    """HSTS header should be present when served over HTTPS in production."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "https",
            "Host": "lgac-assistant-abc123-uc.a.run.app",
        },
    )
    assert response.status_code == 200
    assert "strict-transport-security" in response.headers
    assert "max-age=" in response.headers["strict-transport-security"]


def test_no_hsts_header_on_localhost(client):
    """HSTS header should NOT be present on localhost."""
    response = client.get(
        "/api/health",
        headers={
            "X-Forwarded-Proto": "https",
            "Host": "localhost:9247",
        },
    )
    assert response.status_code == 200
    assert "strict-transport-security" not in response.headers
