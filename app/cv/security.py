import bleach
import io
import zipfile
from app.config.settings import settings
from app.shared.middleware.error_handler import AppException


SUPPORTED_MIME_TYPES = {
    "application/pdf": [".pdf"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    "text/plain": [".txt"],
}


def validate_file_size(file_bytes: bytes, max_mb: int = settings.MAX_UPLOAD_SIZE_MB) -> None:
    """Ensure upload size does not exceed specified limit in megabytes."""
    max_bytes = max_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise AppException(
            message=f"File size exceeds maximum allowed limit of {max_mb}MB.",
            code="FILE_TOO_LARGE",
            status_code=400,
        )


def sniff_mime_type(file_bytes: bytes, declared_filename: str) -> str:
    """
    Inspect magic bytes of file content to detect true MIME type.
    Rejects spoofed file extensions and unsupported formats.
    """
    if not file_bytes:
        raise AppException("Uploaded file is empty.", code="INVALID_FILE", status_code=400)

    # 1. PDF Check (%PDF-)
    if file_bytes.startswith(b"%PDF-"):
        return "application/pdf"

    # 2. DOCX Check (PK\x03\x04 zip header containing Word structures)
    if file_bytes.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                expanded = sum(entry.file_size for entry in entries)
                if len(entries) > 2000 or expanded > settings.MAX_DOCX_EXPANDED_BYTES:
                    raise AppException("DOCX expanded size exceeds allowed limits.", code="FILE_TOO_LARGE", status_code=400)
                if any(entry.flag_bits & 1 for entry in entries):
                    raise AppException("Encrypted DOCX files are unsupported.", code="INVALID_FILE", status_code=400)
                if "[Content_Types].xml" in names and "word/document.xml" in names:
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            pass
        raise AppException("Invalid DOCX archive.", code="INVALID_FILE", status_code=400)

    # 3. Plain Text Check (Valid UTF-8 string)
    try:
        file_bytes.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        pass

    raise AppException(
        message="Unsupported or corrupt file type. Only PDF, DOCX, and plain text UTF-8 files are accepted.",
        code="UNSUPPORTED_FILE_TYPE",
        status_code=400,
    )


def sanitize_text(text: str) -> str:
    """Sanitize extracted text fields to prevent HTML/XSS injection attacks."""
    if not text:
        return ""
    # Strip all HTML tags & unsafe characters
    cleaned = bleach.clean(text, tags=[], strip=True)
    return cleaned.strip()
