from unittest.mock import MagicMock, patch

from lgac_assistant.ingest import (
    _find_section_headings,
    _format_normal_table,
    _has_reversed_text,
    _is_layout_table,
    _remove_repeated_headers,
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


# --- _remove_repeated_headers tests ---


def test_remove_repeated_headers_basic():
    """Lines appearing > threshold times are removed except first occurrence."""
    header = "RULES & REGULATIONS"
    lines = [header, "Some content", header, "More content", header, header]
    text = "\n".join(lines)
    cleaned, removed = _remove_repeated_headers(text, threshold=2)
    assert cleaned.count(header) == 1
    assert removed == 3
    assert "Some content" in cleaned
    assert "More content" in cleaned


def test_remove_repeated_headers_preserves_short_lines():
    """Lines shorter than 10 chars are never treated as headers."""
    text = "Hi\nHi\nHi\nHi\nHi\nHi\nHi"
    cleaned, removed = _remove_repeated_headers(text, threshold=2)
    assert cleaned.count("Hi") == 7
    assert removed == 0


def test_remove_repeated_headers_decorative_dividers():
    """Duplicate decorative divider lines are collapsed."""
    text = "Content A\n----------\nContent B\n----------\nContent C"
    cleaned, removed = _remove_repeated_headers(text)
    assert cleaned.count("----------") == 1
    assert removed == 1


def test_remove_repeated_headers_no_false_positives():
    """Lines appearing <= threshold times are kept."""
    text = "Header Line One\nContent\nHeader Line One\nMore Content\nHeader Line One"
    cleaned, removed = _remove_repeated_headers(text, threshold=3)
    assert cleaned.count("Header Line One") == 3
    assert removed == 0


# --- _is_layout_table tests ---


def test_is_layout_table_empty_headers():
    """Table with all empty headers is a layout table."""
    table = [
        [None, "", "  "],
        ["data1", "data2", "data3"],
    ]
    assert _is_layout_table(table) is True


def test_is_layout_table_single_column():
    """Single-column table is a layout table."""
    table = [["Header"], ["data1"], ["data2"]]
    assert _is_layout_table(table) is True


def test_is_layout_table_real_data():
    """Table with real headers and data is not a layout table."""
    table = [
        ["Name", "Value", "Category"],
        ["Item A", "100", "Golf"],
        ["Item B", "200", "Tennis"],
    ]
    assert _is_layout_table(table) is False


# --- _format_normal_table tests ---


def test_format_normal_table_basic():
    """Normal table formats with header context."""
    table = [
        ["Item", "Price", "Category"],
        ["Shirt", "$50", "Golf"],
        ["Shorts", "$40", "Tennis"],
    ]
    result = _format_normal_table(table)
    assert "Item: Shirt | Price: $50 | Category: Golf" in result
    assert "Item: Shorts | Price: $40 | Category: Tennis" in result


def test_format_normal_table_empty_headers_filtered():
    """Columns with empty headers are skipped."""
    table = [
        ["Item", "", "Price"],
        ["Shirt", "junk", "$50"],
    ]
    result = _format_normal_table(table)
    assert "Item: Shirt" in result
    assert "Price: $50" in result
    assert "junk" not in result


# --- DOCX table extraction tests ---


def test_format_docx_table():
    """DOCX table formats with header context."""
    from lgac_assistant.ingest import _format_docx_table

    # Create mock table with mock rows/cells
    mock_table = MagicMock()
    header_cells = [MagicMock(text="Day"), MagicMock(text="Hours")]
    row1_cells = [MagicMock(text="Monday"), MagicMock(text="9am-5pm")]
    row2_cells = [MagicMock(text="Tuesday"), MagicMock(text="10am-6pm")]

    header_row = MagicMock()
    header_row.cells = header_cells
    data_row1 = MagicMock()
    data_row1.cells = row1_cells
    data_row2 = MagicMock()
    data_row2.cells = row2_cells

    mock_table.rows = [header_row, data_row1, data_row2]
    result = _format_docx_table(mock_table)
    assert "Day: Monday | Hours: 9am-5pm" in result
    assert "Day: Tuesday | Hours: 10am-6pm" in result


def test_format_docx_table_skips_empty_rows():
    """Empty rows in DOCX tables are skipped."""
    from lgac_assistant.ingest import _format_docx_table

    mock_table = MagicMock()
    header_cells = [MagicMock(text="A"), MagicMock(text="B")]
    row1_cells = [MagicMock(text=""), MagicMock(text="")]
    row2_cells = [MagicMock(text="x"), MagicMock(text="y")]

    header_row = MagicMock()
    header_row.cells = header_cells
    data_row1 = MagicMock()
    data_row1.cells = row1_cells
    data_row2 = MagicMock()
    data_row2.cells = row2_cells

    mock_table.rows = [header_row, data_row1, data_row2]
    result = _format_docx_table(mock_table)
    lines = [line for line in result.strip().split("\n") if line.strip()]
    assert len(lines) == 1
    assert "A: x | B: y" in result


# --- Section-aware chunking tests ---


def test_find_section_headings():
    """ALL-CAPS lines are detected as headings."""
    text = "Intro text here\nGUEST POLICIES\nGuests must register\nDRESS CODE\nShirts required"
    headings = _find_section_headings(text)
    heading_texts = [h for _, h in headings]
    assert "GUEST POLICIES" in heading_texts
    assert "DRESS CODE" in heading_texts
    assert "Intro text here" not in heading_texts


def test_chunk_section_prepend():
    """Chunks that don't start with a heading get the heading prepended."""
    # Create text where a heading is in the first chunk but content continues
    # into a second chunk that won't naturally contain the heading.
    heading = "POOL RULES"
    content_after = "Paragraph content. " * 300  # enough to force a second chunk
    text = f"{heading}\n{content_after}"
    chunks = chunk_text(text, "test.pdf", chunk_size=200, chunk_overlap=20)
    assert len(chunks) >= 2
    # First chunk should start with the heading naturally
    assert heading in chunks[0].text
    # Second chunk should have the heading prepended in brackets
    assert chunks[1].text.startswith(f"[{heading}]")


def test_chunk_section_metadata():
    """Chunks with a section heading get 'section' in metadata."""
    text = "GOLF RULES\nPlayers must follow etiquette on the course."
    chunks = chunk_text(text, "test.pdf")
    assert len(chunks) == 1
    assert chunks[0].metadata.get("section") == "GOLF RULES"


def test_chunk_no_duplicate_prepend():
    """If a chunk already starts with the heading, don't prepend again."""
    text = "DINING\nFood and beverage info here."
    chunks = chunk_text(text, "test.pdf")
    assert len(chunks) == 1
    # Should NOT have "[DINING]\nDINING\n..."
    assert chunks[0].text.count("DINING") == 1
