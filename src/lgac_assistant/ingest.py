import logging
import re
from pathlib import Path

from .models import DocumentChunk

logger = logging.getLogger(__name__)


def _reverse_cell_text(cell: str) -> str:
    """Reverse character order within each line and reverse line order.

    Fixes text from rotated PDF cells where characters are reversed
    and lines read bottom-to-top (e.g., 'esuohkaetS\\ns\\'remlaP' → "Palmer's Steakhouse").
    """
    lines = cell.strip().split("\n")
    reversed_lines = [line[::-1] for line in lines]
    reversed_lines.reverse()
    return " ".join(part.strip() for part in reversed_lines if part.strip())


def _has_reversed_text(cells: list[str]) -> bool:
    """Detect reversed text in a list of cell values.

    Checks if non-empty cells contain words (3+ alphabetic chars) that
    end with an uppercase letter and start with lowercase — the signature
    of a reversed proper noun (e.g., 'esuohkaetS' from 'Steakhouse').

    Returns True if a majority of qualifying words match the pattern.
    """
    if not cells:
        return False

    reversed_pattern = re.compile(r"^[a-z].*[A-Z]$")
    qualifying = 0
    matching = 0

    for cell in cells:
        for word in cell.replace("\n", " ").split():
            alpha_chars = sum(1 for c in word if c.isalpha())
            if alpha_chars >= 3:
                qualifying += 1
                if reversed_pattern.match(word):
                    matching += 1

    return qualifying > 0 and matching / qualifying > 0.5


def _extract_item_names(text: str) -> list[str]:
    """Extract item names from pdfplumber text containing Y/N grid data.

    Parses lines like 'Dress Hats (Women) Y Y Y Y Y Y Y Y Y Y'
    to extract 'Dress Hats (Women)'.
    """
    yn_values = {"Y", "N", "L*", "Y**", "Y***"}
    items = []
    for line in text.split("\n"):
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        yn_count = 0
        for p in reversed(parts):
            if p in yn_values:
                yn_count += 1
            else:
                break
        if yn_count >= 5:
            name = " ".join(parts[: len(parts) - yn_count])
            if name:
                items.append(name)
    return items


def _format_reversed_table(
    table: list[list], text: str | None = None
) -> str:
    """Format a table with reversed headers into structured text.

    Fixes reversed column headers, filters empty columns, fills in missing
    row labels from extract_text() output, and produces structured output
    like 'Item | Venue1: Y | Venue2: N | ...'.
    """
    headers_row = table[0]

    # Find non-empty header columns (skip column 0 which is the row label)
    header_map: list[tuple[int, str]] = []
    for i in range(1, len(headers_row)):
        cell = headers_row[i]
        if cell and str(cell).strip():
            header_map.append((i, _reverse_cell_text(str(cell))))

    # Extract item names from text for filling missing row labels
    item_names = _extract_item_names(text) if text else []

    lines = []
    item_idx = 0
    for row in table[1:]:
        # Collect values from non-empty header columns
        vals = []
        for col_i, _ in header_map:
            v = str(row[col_i]).strip() if col_i < len(row) and row[col_i] else ""
            vals.append(v)

        if not any(vals):
            continue  # Skip empty rows

        # Get the label from the row or fall back to item_names
        label = str(row[0]).strip() if row[0] and str(row[0]).strip() else None
        if not label and item_idx < len(item_names):
            label = item_names[item_idx]
        if not label:
            label = "Unknown"

        item_idx += 1

        parts = [label]
        for (_, header_name), v in zip(header_map, vals):
            if v:
                parts.append(f"{header_name}: {v}")

        lines.append(" | ".join(parts))

    return "\n".join(lines)


def _has_orphaned_grid_data(text: str) -> bool:
    """Detect standalone Y/N lines indicating grid table data without column context.

    PyMuPDF sometimes extracts grid tables as individual Y/N values on
    separate lines, with column headers detached at the end of the text.
    """
    yn_values = {"Y", "N", "L*", "Y**"}
    yn_lines = 0
    for line in text.split("\n"):
        stripped = line.strip().rstrip("\t").strip()
        if stripped in yn_values:
            yn_lines += 1
    return yn_lines >= 20


def extract_text_pymupdf(path: Path) -> str:
    """Extract text from PDF using PyMuPDF."""
    import fitz

    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def extract_text_pdfplumber(path: Path) -> str:
    """Extract text from PDF using pdfplumber (better for tables)."""
    import pdfplumber

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Check first row for reversed text (rotated column headers)
                header_cells = [str(c) for c in table[0] if c and str(c).strip()]
                if header_cells and _has_reversed_text(header_cells):
                    pages.append(_format_reversed_table(table, text))
                else:
                    for row in table:
                        cells = [str(c) if c else "" for c in row]
                        pages.append(" | ".join(cells))
    return "\n".join(pages)


def extract_pdf(path: Path) -> str:
    """Extract text from PDF, trying PyMuPDF first, falling back to pdfplumber."""
    text = extract_text_pymupdf(path)
    if len(text.strip()) < 100:
        logger.info(f"PyMuPDF yielded little text for {path.name}, trying pdfplumber")
        text = extract_text_pdfplumber(path)
    else:
        # Quality checks: detect garbled text that PyMuPDF can't handle well
        text_lines = [line.strip() for line in text.split("\n") if line.strip()]
        if _has_reversed_text(text_lines) or _has_orphaned_grid_data(text):
            logger.info(
                f"PyMuPDF output has quality issues for {path.name}, "
                "trying pdfplumber"
            )
            text = extract_text_pdfplumber(path)
    return text


def extract_docx(path: Path) -> str:
    """Extract text from DOCX file."""
    import docx

    doc = docx.Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_document(path: Path) -> str:
    """Extract text from a document based on its extension."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    elif suffix in (".docx", ".doc"):
        return extract_docx(path)
    else:
        raise ValueError(f"Unsupported file type: {suffix}")


def chunk_text(
    text: str,
    source_name: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[DocumentChunk]:
    """Split text into overlapping chunks by approximate token count.

    Uses word-based splitting with ~0.75 words per token as a rough estimate.
    Tries to split at paragraph or sentence boundaries when possible.
    """
    if not text.strip():
        return []

    # Approximate: 1 token ~ 0.75 words, so chunk_size tokens ~ chunk_size * 0.75 words
    # But we'll use character-based chunking for simplicity: ~4 chars per token
    char_limit = chunk_size * 4
    char_overlap = chunk_overlap * 4

    # Clean up text
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    chunks = []
    start = 0

    while start < len(text):
        end = start + char_limit

        if end >= len(text):
            chunk_text_str = text[start:]
        else:
            # Try to break at paragraph boundary
            para_break = text.rfind("\n\n", start + char_limit // 2, end)
            if para_break != -1:
                end = para_break
            else:
                # Try sentence boundary
                sentence_break = text.rfind(". ", start + char_limit // 2, end)
                if sentence_break != -1:
                    end = sentence_break + 1

            chunk_text_str = text[start:end]

        chunk_text_str = chunk_text_str.strip()
        if chunk_text_str:
            chunks.append(
                DocumentChunk(
                    text=chunk_text_str,
                    metadata={
                        "source": source_name,
                        "chunk_index": len(chunks),
                    },
                )
            )

        if end >= len(text):
            break

        start = end - char_overlap

    return chunks


def ingest_documents(
    docs_dir: Path,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[DocumentChunk]:
    """Process all documents in a directory into chunks."""
    all_chunks = []
    supported = (".pdf", ".docx", ".doc")

    if not docs_dir.exists():
        logger.warning(f"Documents directory not found: {docs_dir}")
        return all_chunks

    files = sorted(f for f in docs_dir.iterdir() if f.suffix.lower() in supported)
    logger.info(f"Found {len(files)} documents to process")

    for filepath in files:
        try:
            logger.info(f"Processing: {filepath.name}")
            text = extract_document(filepath)
            chunks = chunk_text(text, filepath.name, chunk_size, chunk_overlap)
            logger.info(f"  -> {len(chunks)} chunks from {filepath.name}")
            all_chunks.extend(chunks)
        except Exception as e:
            logger.error(f"Failed to process {filepath.name}: {e}")

    logger.info(f"Total: {len(all_chunks)} chunks from {len(files)} documents")
    return all_chunks
