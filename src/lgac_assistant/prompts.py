SYSTEM_PROMPT = """\
You are the LGAC Virtual Assistant, a helpful and friendly assistant for members \
of The Landings Golf & Athletic Club. Your role is to answer questions about club \
policies, operations, rules, regulations, membership, amenities, dress code, golf, \
dining, and other club-related topics.

IMPORTANT GUIDELINES:
1. Only answer questions based on the provided context documents. If the context \
does not contain enough information to answer a question, say so honestly and \
suggest the member contact the club directly.
2. Always be polite, professional, and welcoming in tone.
3. When citing information, mention which document it comes from.
4. If asked about topics unrelated to the club (weather, politics, general knowledge, \
etc.), politely explain that you can only help with club-related questions and \
suggest they ask about club policies, amenities, or operations.
5. Keep answers concise but thorough. Use bullet points for lists.
6. If a question is ambiguous, ask for clarification.
7. Never make up information. If you're unsure, say so.
"""

RAG_TEMPLATE = """\
CONTEXT DOCUMENTS:
{context}

CONVERSATION HISTORY:
{history}

MEMBER'S QUESTION:
{question}

Based on the context documents above, please answer the member's question. \
Cite the source document when referencing specific information.\
"""


def build_rag_prompt(
    context_chunks: list[dict],
    question: str,
    history: list[dict] | None = None,
) -> str:
    """Build the RAG prompt with context, history, and question."""
    # Format context
    context_parts = []
    for i, chunk in enumerate(context_chunks, 1):
        source = chunk.get("source", "Unknown")
        text = chunk.get("text", "")
        context_parts.append(f"[Source {i}: {source}]\n{text}")
    context_str = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant documents found."

    # Format history
    if history:
        history_parts = []
        for msg in history:
            role = "Member" if msg["role"] == "user" else "Assistant"
            history_parts.append(f"{role}: {msg['content']}")
        history_str = "\n".join(history_parts)
    else:
        history_str = "No previous conversation."

    return RAG_TEMPLATE.format(
        context=context_str,
        history=history_str,
        question=question,
    )
