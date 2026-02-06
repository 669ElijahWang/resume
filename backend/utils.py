import re
from pathlib import Path
from typing import Dict, Optional

import pdfplumber


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not cleaned:
        cleaned = "resume"
    return cleaned[:120]


def extract_pdf_text(file_path: Path) -> str:
    text_parts = []
    with pdfplumber.open(str(file_path)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def extract_email(text: str) -> Optional[str]:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def extract_phone(text: str) -> Optional[str]:
    match = re.search(r"(\+?\d[\d\s\-]{7,}\d)", text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(0)).strip()


def backfill_contact(result: Dict[str, str], resume_text: str, file_name: str) -> Dict[str, str]:
    name = result.get("name") or ""
    if not name and file_name:
        name = Path(file_name).stem

    email = result.get("email") or extract_email(resume_text) or ""
    phone = result.get("phone") or extract_phone(resume_text) or ""

    return {
        "name": name.strip(),
        "email": email.strip(),
        "phone": phone.strip(),
    }
