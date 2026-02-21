from lgac_assistant.models import DocumentChunk
from lgac_assistant.vectorstore import VectorStore


def test_add_and_query(temp_dir):
    store = VectorStore(temp_dir)
    chunks = [
        DocumentChunk(text="The dress code requires collared shirts on the golf course.",
                       metadata={"source": "dresscode.pdf", "chunk_index": 0}),
        DocumentChunk(text="The pool is open from 9am to 8pm during summer months.",
                       metadata={"source": "hours.pdf", "chunk_index": 0}),
        DocumentChunk(text="Annual dues for full membership are $5000.",
                       metadata={"source": "dues.pdf", "chunk_index": 0}),
    ]
    added = store.add_chunks(chunks)
    assert added == 3
    assert store.count() == 3

    results = store.query("What should I wear to play golf?", n_results=2)
    assert len(results) == 2
    # The dress code chunk should be most relevant
    assert "dress code" in results[0].text.lower() or "collared" in results[0].text.lower()


def test_empty_store(temp_dir):
    store = VectorStore(temp_dir)
    assert store.count() == 0
    results = store.query("test query")
    assert results == []


def test_reset(temp_dir):
    store = VectorStore(temp_dir)
    chunks = [
        DocumentChunk(text="Test content", metadata={"source": "test.pdf", "chunk_index": 0}),
    ]
    store.add_chunks(chunks)
    assert store.count() == 1
    store.reset()
    assert store.count() == 0
