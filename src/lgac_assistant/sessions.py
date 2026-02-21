import time
import uuid


class Session:
    """A single user session with conversation history."""

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.history: list[dict] = []
        self.last_active = time.time()

    def add_message(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        self.last_active = time.time()

    def touch(self):
        self.last_active = time.time()

    def is_expired(self, expiry_minutes: int) -> bool:
        return (time.time() - self.last_active) > (expiry_minutes * 60)


class SessionManager:
    """In-memory session store with expiry."""

    def __init__(self, expiry_minutes: int = 30):
        self.sessions: dict[str, Session] = {}
        self.expiry_minutes = expiry_minutes

    def create_session(self) -> Session:
        self._cleanup()
        session = Session()
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        self._cleanup()
        session = self.sessions.get(session_id)
        if session and not session.is_expired(self.expiry_minutes):
            session.touch()
            return session
        if session:
            del self.sessions[session_id]
        return None

    def _cleanup(self):
        expired = [
            sid
            for sid, s in self.sessions.items()
            if s.is_expired(self.expiry_minutes)
        ]
        for sid in expired:
            del self.sessions[sid]
