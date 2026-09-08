import pytest
from app.cv.security import validate_file_size, sniff_mime_type, sanitize_text
from app.shared.middleware.error_handler import AppException


def test_file_size_validation():
    small_file = b"a" * (1024 * 1024)  # 1 MB
    validate_file_size(small_file, max_mb=10)

    large_file = b"a" * (11 * 1024 * 1024)  # 11 MB
    with pytest.raises(AppException) as exc_info:
        validate_file_size(large_file, max_mb=10)
    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_mime_type_sniffing():
    # PDF magic bytes
    pdf_bytes = b"%PDF-1.5 header content..."
    assert sniff_mime_type(pdf_bytes, "fake_doc.pdf") == "application/pdf"
    assert sniff_mime_type(pdf_bytes, "fake_doc.docx") == "application/pdf"  # Sniffs true type despite wrong extension!

    # DOCX zip header
    docx_bytes = b"PK\x03\x04 word/document.xml content"
    assert sniff_mime_type(docx_bytes, "resume.docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    # Plain text UTF-8
    txt_bytes = b"John Doe\nSoftware Engineer\nPython, FastAPI"
    assert sniff_mime_type(txt_bytes, "cv.txt") == "text/plain"

    # Empty file
    with pytest.raises(AppException) as exc:
        sniff_mime_type(b"", "empty.txt")
    assert exc.value.code == "INVALID_FILE"


def test_text_sanitization():
    unsafe_input = "John Doe <script>alert('xss')</script> <img src=x onerror=alert(1)>"
    cleaned = sanitize_text(unsafe_input)
    assert "<script>" not in cleaned
    assert "<img>" not in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned
