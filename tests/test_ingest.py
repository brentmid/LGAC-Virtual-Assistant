from lgac_assistant.ingest import chunk_text


def test_chunk_text_basic():
    text = "Hello world. " * 200  # ~2600 chars
    chunks = chunk_text(text, "test.pdf", chunk_size=200, chunk_overlap=50)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.source_name == "test.pdf"
        assert len(chunk.text) > 0


def test_chunk_text_empty():
    chunks = chunk_text("", "test.pdf")
    assert chunks == []


def test_chunk_text_whitespace():
    chunks = chunk_text("   \n\n  ", "test.pdf")
    assert chunks == []


def test_chunk_text_short():
    text = "This is a short document."
    chunks = chunk_text(text, "short.pdf")
    assert len(chunks) == 1
    assert chunks[0].text == text
    assert chunks[0].source_name == "short.pdf"
    assert chunks[0].chunk_index == 0


def test_chunk_metadata():
    text = "Word " * 1000
    chunks = chunk_text(text, "meta.pdf", chunk_size=100, chunk_overlap=20)
    assert len(chunks) > 1
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["source"] == "meta.pdf"
        assert chunk.metadata["chunk_index"] == i
