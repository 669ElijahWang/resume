import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "app.db"

QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen3-max")
QWEN_TIMEOUT = float(os.getenv("QWEN_TIMEOUT", "60"))
QWEN_MAX_RETRIES = int(os.getenv("QWEN_MAX_RETRIES", "2"))
QWEN_RETRY_BACKOFF = float(os.getenv("QWEN_RETRY_BACKOFF", "0.8"))

MAX_FILES = int(os.getenv("MAX_FILES", "100"))
MAX_TEXT_CHARS = int(os.getenv("MAX_TEXT_CHARS", "12000"))

DEFAULT_MODULES = [
    {"name": "SkillMatch", "desc": "Match of required skills and tools to JD."},
    {"name": "ProjectExperience", "desc": "Relevance and depth of project work."},
    {"name": "YearsExperience", "desc": "Years and quality of work experience."},
    {"name": "Education", "desc": "Education background relevance and rigor."},
    {"name": "Collaboration", "desc": "Communication and teamwork signals."},
    {"name": "Stability", "desc": "Job stability and tenure consistency."},
]
