import io
import docx
import pypdf
from app.shared.middleware.error_handler import AppException


def extract_text_from_file(file_bytes: bytes, mime_type: str) -> str:
    """
    Extract raw text content from uploaded file bytes based on sniffed MIME type.
    """
    if mime_type == "application/pdf":
        return _extract_pdf(file_bytes)
    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx(file_bytes)
    elif mime_type == "text/plain":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise AppException("Unsupported format for text extraction.", code="UNSUPPORTED_FORMAT", status_code=400)


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        extracted_pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_pages.append(text)
        full_text = "\n".join(extracted_pages).strip()
        if not full_text:
            raise AppException("Could not extract readable text from PDF file.", code="EXTRACTION_FAILED", status_code=400)
        return full_text
    except Exception as exc:
        if isinstance(exc, AppException):
            raise
        raise AppException(f"Failed to parse PDF file: {str(exc)}", code="CORRUPT_FILE", status_code=400)


def _extract_docx(file_bytes: bytes) -> str:
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        full_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip()]).strip()
        if not full_text:
            raise AppException("Could not extract readable text from DOCX file.", code="EXTRACTION_FAILED", status_code=400)
        return full_text
    except Exception as exc:
        if isinstance(exc, AppException):
            raise
        raise AppException(f"Failed to parse DOCX file: {str(exc)}", code="CORRUPT_FILE", status_code=400)
