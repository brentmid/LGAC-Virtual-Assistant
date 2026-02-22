import json
import os

from lgac_assistant.feedback import FeedbackStore
from lgac_assistant.models import FeedbackRecord


def _make_record(**overrides):
    defaults = {
        "timestamp": "2026-02-22T12:00:00+00:00",
        "question": "What is the dress code?",
        "response": "Collared shirts are required.",
        "feedback": "Great answer!",
        "session_id": "test-session-123",
    }
    defaults.update(overrides)
    return FeedbackRecord(**defaults)


def test_add_creates_file(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    store = FeedbackStore(path)
    store.add(_make_record())
    assert os.path.exists(path)
    data = json.loads(open(path).read())
    assert len(data) == 1
    assert data[0]["feedback"] == "Great answer!"


def test_add_appends(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    store = FeedbackStore(path)
    store.add(_make_record(feedback="First"))
    store.add(_make_record(feedback="Second"))
    data = json.loads(open(path).read())
    assert len(data) == 2
    assert data[0]["feedback"] == "First"
    assert data[1]["feedback"] == "Second"


def test_get_all_returns_newest_first(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    store = FeedbackStore(path)
    store.add(_make_record(feedback="First"))
    store.add(_make_record(feedback="Second"))
    records = store.get_all()
    assert len(records) == 2
    assert records[0].feedback == "Second"
    assert records[1].feedback == "First"


def test_get_all_empty_file(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    store = FeedbackStore(path)
    records = store.get_all()
    assert records == []


def test_get_all_corrupt_file(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    with open(path, "w") as f:
        f.write("not json")
    store = FeedbackStore(path)
    records = store.get_all()
    assert records == []


def test_get_all_non_list_json(temp_dir):
    path = os.path.join(temp_dir, "feedback.json")
    with open(path, "w") as f:
        f.write('{"key": "value"}')
    store = FeedbackStore(path)
    records = store.get_all()
    assert records == []
