import json
import logging
from pathlib import Path

from .models import FeedbackRecord

logger = logging.getLogger(__name__)


class FeedbackStore:
    """Persists feedback records to a JSON file."""

    def __init__(self, file_path: str = "./feedback.json"):
        self.path = Path(file_path)

    def add(self, record: FeedbackRecord) -> None:
        records = self._read()
        records.append(record.model_dump())
        self._write(records)

    def get_all(self) -> list[FeedbackRecord]:
        records = self._read()
        items = [FeedbackRecord(**r) for r in reversed(records)]
        return items

    def _read(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            logger.warning("Could not read feedback file %s, starting fresh", self.path)
            return []

    def _write(self, records: list[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records, indent=2) + "\n")
