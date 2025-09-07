# utils/parser.py
import fitz  # PyMuPDF
import docx
from werkzeug.datastructures import FileStorage
from io import BytesIO

def extract_text(file: FileStorage) -> str:
    """
    Extract text from an uploaded file (PDF or DOCX).
    Returns plain text string.
    """
    filename = (file.filename or "").lower()
    data = file.read()
    try:
        file.seek(0)
    except Exception:
        pass

    # PDF
    if filename.endswith(".pdf"):
        text_parts = []
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            for page in doc:
                page_text = page.get_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts).strip()
        except Exception as e:
            # As fallback, try decoding raw
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                raise e

    # DOCX
    if filename.endswith(".docx") or filename.endswith(".doc"):
        try:
            # python-docx expects a file-like object
            docx_file = BytesIO(data)
            doc = docx.Document(docx_file)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs).strip()
        except Exception:
            try:
                return data.decode("utf-8", errors="ignore")
            except Exception:
                return ""

    # Fallback
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""
