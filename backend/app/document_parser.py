from hashlib import sha256
from pathlib import PurePath
import fitz
from . import config
from .schemas import Document
from .bangla_sentence_segmenter import segment


class DocumentError(ValueError):
    pass


def parse_document(data: bytes, filename: str, query=False) -> Document:
    filename = PurePath(filename.replace("\\", "/")).name[:200]
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix not in ("pdf", "txt"):
        raise DocumentError("Only PDF and UTF-8 TXT files are supported.")
    if not data:
        raise DocumentError("The uploaded file is empty.")
    if len(data) > config.MAX_UPLOAD:
        raise DocumentError("The file exceeds the upload size limit.")
    digest = sha256(data).hexdigest()
    doc_id = ("Q" if query else "D") + digest[:24]
    page_count, locations, warnings = None, None, []
    if suffix == "txt":
        try:
            text = data.decode(
                "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            )
        except UnicodeError as exc:
            raise DocumentError(
                "Cannot decode this TXT file. Save it as UTF-8 and upload again."
            ) from exc
        if "\x00" in text:
            raise DocumentError("The TXT file contains binary data.")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    else:
        if not data.startswith(b"%PDF-"):
            raise DocumentError("The file does not contain a valid PDF header.")
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise DocumentError("Password-protected PDFs must be unlocked first.")
                page_count = len(pdf)
                if page_count > config.MAX_PDF_PAGES:
                    raise DocumentError("This PDF exceeds the page limit.")
                parts, locations, offset = [], [], 0
                for pn, page in enumerate(pdf, 1):
                    value = page.get_text("text", sort=True)
                    if not value.strip():
                        warnings.append(f"Page {pn} has no extractable text; OCR may be required.")
                    for ln, line in enumerate(value.splitlines(keepends=True), 1):
                        locations.append((offset, offset + len(line), pn, ln))
                        offset += len(line)
                    parts.append(value)
                    parts.append("\n\n")
                    offset += 2
                    if offset > config.MAX_TEXT_CHARS:
                        raise DocumentError("Extracted text exceeds the character limit.")
                text = "".join(parts)
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError(
                "The PDF could not be read. It may be malformed or unsupported."
            ) from exc
        if not text.strip():
            raise DocumentError(
                "This PDF has no extractable text. OCR is required for scanned PDFs."
            )
    if len(text) > config.MAX_TEXT_CHARS:
        raise DocumentError("Extracted text exceeds the character limit.")
    sentences = segment(text, doc_id, filename, locations, suffix == "pdf")
    limit = config.MAX_QUERY_SENTENCES if query else config.MAX_SOURCE_SENTENCES
    if not sentences:
        raise DocumentError("No usable sentences were found in this document.")
    if len(sentences) > limit:
        raise DocumentError(f"This document exceeds the {limit}-sentence limit.")
    return Document(
        document_id=doc_id,
        filename=filename,
        file_type=suffix.upper(),
        size_bytes=len(data),
        content_hash=digest,
        page_count=page_count,
        text=text,
        sentences=sentences,
        warnings=warnings,
    )
