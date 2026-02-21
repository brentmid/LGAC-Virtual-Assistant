import os
import tempfile

import pytest

# Set test environment variables before importing app modules
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("APP_PASSWORD", "testpass")


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d
