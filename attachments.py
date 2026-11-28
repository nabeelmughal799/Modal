"""Safe, size-limited parsing for files uploaded in a chat."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import zipfile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_FILE_BYTES = 20 * 1024 * 1024
MAX_ATTACHMENTS = 3
MAX_PDF_PAGES = 20
MAX_DOCUMENT_CHARS = 30_000


@dataclass(frozen=True)
class PreparedAttachment:
    file_name: str
    mime_type: str
    data: bytes
    extracted_text: str = ""


def _limited_text(text: str) -> str:
    if len(text) > MAX_DOCUMENT_CHARS:
        return text[:MAX_DOCUMENT_CHARS] + "\n[Document text truncated at 30,000 characters.]"
    return text


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except (PdfReadError, OSError) as error:
        raise ValueError("This PDF could not be read.") from error

    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs cannot be read.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"PDFs are limited to {MAX_PDF_PAGES} pages.")

    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError(
            "I couldn't read this scanned PDF because it has no selectable text."
        )
    return _limited_text(text)


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            uncompressed_size = sum(item.file_size for item in archive.infolist())
            if len(archive.infolist()) > 1000 or uncompressed_size > MAX_TOTAL_FILE_BYTES:
                raise ValueError("This DOCX expands beyond the document size limit.")
        document = Document(BytesIO(data))
    except (OSError, ValueError, zipfile.BadZipFile, PackageNotFoundError) as error:
        if isinstance(error, ValueError):
            raise
        raise ValueError("This DOCX file could not be read.") from error

    blocks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        for row in table.rows:
            blocks.append(" | ".join(cell.text for cell in row.cells))
    text = "\n".join(blocks).strip()
    if not text:
        raise ValueError("This DOCX contains no readable text.")
    return _limited_text(text)


def prepare_attachment(file_name: str, data: bytes) -> PreparedAttachment:
    """Validate an upload and extract text where the format supports it."""
    safe_name = Path(file_name).name
    suffix = Path(safe_name).suffix.lower()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Each file must be {MAX_FILE_BYTES // (1024 * 1024)} MB or smaller.")

    if suffix == ".pdf":
        return PreparedAttachment(safe_name, "application/pdf", data, _pdf_text(data))
    if suffix == ".docx":
        return PreparedAttachment(
            safe_name,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            data,
            _docx_text(data),
        )
    if suffix == ".txt":
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as error:
            raise ValueError("TXT files must use UTF-8 encoding.") from error
        if not text:
            raise ValueError("This TXT file contains no readable text.")
        return PreparedAttachment(safe_name, "text/plain", data, _limited_text(text))
    if suffix in (".jpg", ".jpeg", ".png"):
        try:
            with Image.open(BytesIO(data)) as image:
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise ValueError("This image could not be read.") from error
        mime_type = "image/png" if suffix == ".png" else "image/jpeg"
        return PreparedAttachment(safe_name, mime_type, data)

    raise ValueError("Supported file types are PDF, DOCX, TXT, JPG, and PNG.")


def validate_attachments(files: list[tuple[str, bytes]]) -> list[PreparedAttachment]:
    if len(files) > MAX_ATTACHMENTS:
        raise ValueError(f"Attach no more than {MAX_ATTACHMENTS} files per message.")
    if sum(len(data) for _, data in files) > MAX_TOTAL_FILE_BYTES:
        raise ValueError("Attachments for one message must total 20 MB or less.")
    return [prepare_attachment(name, data) for name, data in files]
