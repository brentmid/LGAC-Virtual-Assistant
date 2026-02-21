import logging
import re
from pathlib import Path

from .models import DocumentChunk

logger = logging.getLogger(__name__)


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
