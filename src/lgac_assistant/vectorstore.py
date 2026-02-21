import logging
from pathlib import Path

import chromadb

from .models import DocumentChunk

logger = logging.getLogger(__name__)

COLLECTION_NAME = "lgac_documents"


class VectorStore:
    """Wrapper around ChromaDB for document storage and retrieval."""

    def __init__(self, persist_dir: str | Path):
        self.persist_dir = Path(persist_dir)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(self, chunks: list[DocumentChunk]) -> int:
        """Add document chunks to the vector store. Returns number added."""
        if not chunks:
            return 0

        ids = [f"chunk_{i}" for i in range(len(chunks))]
        documents = [c.text for c in chunks]
        metadatas = [c.metadata for c in chunks]

        # ChromaDB has a batch limit, process in batches of 5000
        batch_size = 5000
        added = 0
        for i in range(0, len(chunks), batch_size):
            end = min(i + batch_size, len(chunks))
            self.collection.add(
                ids=ids[i:end],
                documents=documents[i:end],
                metadatas=metadatas[i:end],
            )
            added += end - i

        logger.info(f"Added {added} chunks to vector store")
        return added

    def query(self, query_text: str, n_results: int = 5) -> list[DocumentChunk]:
        """Query the vector store for relevant chunks."""
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[query_text],
            n_results=min(n_results, self.collection.count()),
        )

        chunks = []
        if results["documents"] and results["metadatas"]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                chunks.append(DocumentChunk(text=doc, metadata=meta))

        return chunks

    def count(self) -> int:
        """Return the number of chunks in the store."""
        return self.collection.count()

    def reset(self):
        """Delete the collection and recreate it."""
        self.client.delete_collection(COLLECTION_NAME)
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
