import time

from lgac_assistant.sessions import Session, SessionManager


def test_session_creation():
    session = Session()
    assert session.id
    assert session.history == []
    assert not session.is_expired(30)


def test_session_add_message():
    session = Session()
    session.add_message("user", "Hello")
    session.add_message("assistant", "Hi there")
    assert len(session.history) == 2
    assert session.history[0] == {"role": "user", "content": "Hello"}
    assert session.history[1] == {"role": "assistant", "content": "Hi there"}


def test_session_expiry():
    session = Session()
    session.last_active = time.time() - 3600  # 1 hour ago
    assert session.is_expired(30)
    assert not session.is_expired(120)


def test_session_manager_create():
    mgr = SessionManager(expiry_minutes=30)
    session = mgr.create_session()
    assert session.id in mgr.sessions


def test_session_manager_get():
    mgr = SessionManager(expiry_minutes=30)
    session = mgr.create_session()
    retrieved = mgr.get_session(session.id)
    assert retrieved is not None
    assert retrieved.id == session.id


def test_session_manager_get_invalid():
    mgr = SessionManager(expiry_minutes=30)
    result = mgr.get_session("nonexistent")
    assert result is None


def test_session_manager_expiry_cleanup():
    mgr = SessionManager(expiry_minutes=1)
    session = mgr.create_session()
    session.last_active = time.time() - 120  # 2 minutes ago
    result = mgr.get_session(session.id)
    assert result is None
    assert session.id not in mgr.sessions
