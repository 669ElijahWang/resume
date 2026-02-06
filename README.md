# Resume Screening Platform

Batch upload PDF resumes with a single JD, score them via Qwen3, and export ranked results to Excel or Markdown.

## Requirements
- Python 3.10+
- Qwen API key (QWEN_API_KEY)

## Setup
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
```

Create a `.env` file in the repo root:
```bash
QWEN_API_KEY=your_key_here
QWEN_MODEL=qwen3-max
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
```

## Run
```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser.

## Notes
- Upload limit: 100 PDFs per job (configurable via `MAX_FILES`).
- Data is stored in `data/app.db`, uploads in `data/uploads/`.
- Exports are generated on-demand via API endpoints.



uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload