import logging

import anthropic

from .models import ChatResponse, SourceInfo
from .prompts import SYSTEM_PROMPT, build_rag_prompt
from .vectorstore import VectorStore

logger = logging.getLogger(__name__)


class RAGEngine:
    """Retrieval-Augmented Generation engine using ChromaDB and Claude."""

    def __init__(self, vector_store: VectorStore, model: str, api_key: str):
        self.vector_store = vector_store
        self.model = model
        self.client = anthropic.Anthropic(api_key=api_key)

    def query(
        self,
        question: str,
        history: list[dict] | None = None,
        top_k: int = 5,
    ) -> ChatResponse:
        """Retrieve relevant chunks and generate an answer."""
        # Retrieve relevant chunks
        chunks = self.vector_store.query(question, n_results=top_k)
        logger.info(f"Retrieved {len(chunks)} chunks for query: {question[:80]}...")

        # Build context for prompt
        context_items = [
            {"source": c.source_name, "text": c.text}
            for c in chunks
        ]

        # Build the RAG prompt
        user_prompt = build_rag_prompt(context_items, question, history)

        # Call Claude
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        answer = response.content[0].text

        # Build source citations from retrieved chunks
        seen_sources = set()
        sources = []
        for chunk in chunks:
            source_name = chunk.source_name
            if source_name not in seen_sources:
                seen_sources.add(source_name)
                sources.append(
                    SourceInfo(
                        document=source_name,
                        excerpt=chunk.text[:150] + "..." if len(chunk.text) > 150 else chunk.text,
                    )
                )

        return ChatResponse(answer=answer, sources=sources)
