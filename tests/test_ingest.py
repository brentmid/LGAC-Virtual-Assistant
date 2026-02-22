from unittest.mock import MagicMock, patch

from lgac_assistant.ingest import (
    _has_reversed_text,
    _reverse_cell_text,
    chunk_text,
    extract_text_pdfplumber,
)


def test_reverse_cell_text_single_line():
    assert _reverse_cell_text("esuohkaetS") == "Steakhouse"


def test_reverse_cell_text_multi_line():
    # Multi-line reversed cell: lines reversed char-by-char, line order bottom-to-top
    cell = "esuohkaetS\ns'remlaP"
    assert _reverse_cell_text(cell) == "Palmer's Steakhouse"


def test_reverse_cell_text_complex():
    cell = "llirG\nlatsaoC\nA\nkeerC\nreeD"
    assert _reverse_cell_text(cell) == "Deer Creek A Coastal Grill"


def test_has_reversed_text_positive():
    cells = [
        "esuohkaetS\ns'remlaP",
        "nrevaT\ns'einrA",
        "llirG\nlatsaoC\nA\nkeerC\nreeD",
    ]
    assert _has_reversed_text(cells) is True


def test_has_reversed_text_negative():
    cells = ["Palmer's Steakhouse", "Arnie's Tavern", "Deer Creek A Coastal Grill"]
    assert _has_reversed_text(cells) is False


def test_has_reversed_text_empty():
    assert _has_reversed_text([]) is False


def test_has_reversed_text_short_words():
    # Words with <3 alpha chars should be ignored
    cells = ["AB", "xy", "1", ""]
    assert _has_reversed_text(cells) is False


def test_pdfplumber_table_with_reversed_headers():
    """Test that tables with reversed headers produce structured output."""
    # Simulate a pdfplumber page with reversed headers and a table
    table = [
        # Header row: None label, reversed venue names with empty cols
        [None, "esuohkaetS\ns'remlaP", "", "nrevaT\ns'einrA"],
        # Empty row
        [None, "", "", ""],
        # Data row with label
        ["Shirts", "Y", "", "N"],
        # Data row without label (merged cell)
        [None, "N", "", "Y"],
    ]
    text = "Shirts Y Y Y Y N\nPants N N N N Y"

    mock_page = MagicMock()
    mock_page.extract_text.return_value = text
    mock_page.extract_tables.return_value = [table]

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = lambda self: self
    mock_pdf.__exit__ = MagicMock(return_value=False)

    with patch("pdfplumber.open", return_value=mock_pdf):
        from pathlib import Path

        result = extract_text_pdfplumber(Path("fake.pdf"))

    # Should contain fixed header names and structured format
    assert "Palmer's Steakhouse" in result
    assert "Arnie's Tavern" in result
    # First data row uses its own label
    assert "Shirts | Palmer's Steakhouse: Y | Arnie's Tavern: N" in result
    # Second data row fills label from text item names
    assert "Pants | Palmer's Steakhouse: N | Arnie's Tavern: Y" in result


def test_extract_pdf_quality_fallthrough():
    """Verify PyMuPDF-to-pdfplumber fallthrough on orphaned grid data."""
    # Simulate PyMuPDF output with standalone Y/N lines (orphaned grid data)
    pymupdf_text = "Item A\n" + "Y\n" * 30 + "Venue Name\n"
    pdfplumber_text = "Better extraction result"

    with (
        patch(
            "lgac_assistant.ingest.extract_text_pymupdf", return_value=pymupdf_text
        ),
        patch(
            "lgac_assistant.ingest.extract_text_pdfplumber",
            return_value=pdfplumber_text,
        ),
    ):
        from pathlib import Path

        from lgac_assistant.ingest import extract_pdf

        result = extract_pdf(Path("test.pdf"))

    assert result == pdfplumber_text


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
