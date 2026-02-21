from lgac_assistant.prompts import build_rag_prompt


def test_build_rag_prompt_basic():
    context = [{"source": "rules.pdf", "text": "Members must follow dress code."}]
    prompt = build_rag_prompt(context, "What are the rules?")
    assert "rules.pdf" in prompt
    assert "dress code" in prompt
    assert "What are the rules?" in prompt
    assert "No previous conversation" in prompt


def test_build_rag_prompt_with_history():
    context = [{"source": "hours.pdf", "text": "Pool opens at 9am."}]
    history = [
        {"role": "user", "content": "When does the pool open?"},
        {"role": "assistant", "content": "The pool opens at 9am."},
    ]
    prompt = build_rag_prompt(context, "What about weekends?", history)
    assert "Pool opens at 9am" in prompt
    assert "When does the pool open?" in prompt
    assert "What about weekends?" in prompt
    assert "Member:" in prompt
    assert "Assistant:" in prompt


def test_build_rag_prompt_empty_context():
    prompt = build_rag_prompt([], "Any question?")
    assert "No relevant documents found" in prompt


def test_build_rag_prompt_multiple_sources():
    context = [
        {"source": "doc1.pdf", "text": "First document content."},
        {"source": "doc2.pdf", "text": "Second document content."},
    ]
    prompt = build_rag_prompt(context, "Tell me about these")
    assert "doc1.pdf" in prompt
    assert "doc2.pdf" in prompt
    assert "Source 1" in prompt
    assert "Source 2" in prompt
