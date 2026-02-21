#!/usr/bin/env python3
"""CLI script to build the ChromaDB vector index from club documents."""

import logging
import sys
from pathlib import Path

# Add src to path so we can import the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lgac_assistant.config import get_settings
from lgac_assistant.ingest import ingest_documents
from lgac_assistant.vectorstore import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    settings = get_settings()
    docs_dir = settings.docs_path
    persist_dir = settings.chroma_path

    logger.info(f"Documents directory: {docs_dir}")
    logger.info(f"Vector store directory: {persist_dir}")

    if not docs_dir.exists():
        logger.error(f"Documents directory not found: {docs_dir}")
        sys.exit(1)

    # Process documents into chunks
    chunks = ingest_documents(
        docs_dir,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    if not chunks:
        logger.error("No chunks produced. Check your documents.")
        sys.exit(1)

    # Store in ChromaDB
    store = VectorStore(persist_dir)
    store.reset()  # Start fresh
    added = store.add_chunks(chunks)

    logger.info(f"Ingestion complete: {added} chunks indexed")
    logger.info(f"Vector store saved to: {persist_dir}")

    # Quick verification
    test_query = "dress code"
    results = store.query(test_query, n_results=3)
    logger.info(f"\nVerification query: '{test_query}'")
    for i, r in enumerate(results, 1):
        logger.info(f"  Result {i}: [{r.source_name}] {r.text[:100]}...")


if __name__ == "__main__":
    main()
