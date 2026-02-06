import json
import queue
import threading
import uuid
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .db import (
    count_resumes,
    create_job,
    create_resume,
    get_job,
    get_resume,
    init_db,
    list_resumes,
    update_resume,
)
from .qwen import score_resume
from .report import build_excel, build_markdown
from .settings import DEFAULT_MODULES, MAX_FILES, UPLOAD_DIR
from .utils import backfill_contact, extract_pdf_text, safe_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"

app = FastAPI(title="Resume Screening Platform")

task_queue: "queue.Queue[str]" = queue.Queue()
worker_started = False
worker_lock = threading.Lock()


def _start_worker() -> None:
    global worker_started
    with worker_lock:
        if worker_started:
            return
        worker_started = True
        thread = threading.Thread(target=_worker_loop, daemon=True)
        thread.start()


def _worker_loop() -> None:
    while True:
        resume_id = task_queue.get()
        if resume_id is None:
            task_queue.task_done()
            break
        try:
            _process_resume(resume_id)
        finally:
            task_queue.task_done()


def _process_resume(resume_id: str) -> None:
    resume = get_resume(resume_id)
    if not resume:
        return
    update_resume(resume_id, {"status": "processing", "error": None})

    job = get_job(resume["job_id"])
    if not job:
        update_resume(resume_id, {"status": "error", "error": "任务不存在"})
        return

    try:
        text = extract_pdf_text(Path(resume["file_path"]))
        result = score_resume(job["jd_text"], text)
        contact = backfill_contact(result, text, resume["file_name"])
        update_resume(
            resume_id,
            {
                "status": "done",
                "name": contact["name"] or result.get("name", ""),
                "phone": contact["phone"] or result.get("phone", ""),
                "email": contact["email"] or result.get("email", ""),
                "total_score": result.get("total_score"),
                "modules_json": json.dumps(result.get("modules", [])),
                "summary": result.get("summary", ""),
                "raw_json": json.dumps(result.get("raw", {})),
            },
        )
    except Exception as exc:
        update_resume(resume_id, {"status": "error", "error": str(exc)})


@app.on_event("startup")
def _startup() -> None:
    init_db()
    _start_worker()


@app.get("/api/health")
def health() -> JSONResponse:
    return JSONResponse({"ok": True})


@app.post("/api/upload")
async def upload_resumes(
    jd: str = Form(...), files: List[UploadFile] = File(...)
) -> JSONResponse:
    if not jd.strip():
        raise HTTPException(status_code=400, detail="请填写 JD。")
    if not files:
        raise HTTPException(status_code=400, detail="请上传 PDF 文件。")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"最多上传 {MAX_FILES} 份简历。")

    job_id = uuid.uuid4().hex
    create_job(job_id, jd.strip())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件。")

        resume_id = uuid.uuid4().hex
        safe_name = safe_filename(file.filename)
        file_path = job_dir / f"{resume_id}_{safe_name}"
        content = await file.read()
        file_path.write_bytes(content)
        create_resume(resume_id, job_id, file.filename, str(file_path), "queued")
        task_queue.put(resume_id)

    return JSONResponse({"job_id": job_id, "count": len(files)})


@app.get("/api/jobs/{job_id}/status")
def job_status(job_id: str) -> JSONResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    counts = count_resumes(job_id)
    return JSONResponse(
        {
            "job_id": job_id,
            "total": counts.get("total", 0),
            "queued": counts.get("queued", 0),
            "processing": counts.get("processing", 0),
            "done": counts.get("done", 0),
            "error": counts.get("error", 0),
        }
    )


@app.get("/api/jobs/{job_id}/results")
def job_results(job_id: str) -> JSONResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    items = []
    for resume in list_resumes(job_id):
        modules = resume.get("modules_json")
        try:
            modules = json.loads(modules) if modules else []
        except json.JSONDecodeError:
            modules = []
        items.append(
            {
                "resume_id": resume["id"],
                "name": resume.get("name") or "",
                "phone": resume.get("phone") or "",
                "email": resume.get("email") or "",
                "total_score": resume.get("total_score"),
                "summary": resume.get("summary") or "",
                "modules": modules,
                "status": resume.get("status"),
                "error": resume.get("error") or "",
            }
        )

    items.sort(
        key=lambda x: x["total_score"] if x["total_score"] is not None else -1,
        reverse=True,
    )
    return JSONResponse(
        {
            "job_id": job_id,
            "modules": [m["name"] for m in DEFAULT_MODULES],
            "items": items,
        }
    )


@app.get("/api/jobs/{job_id}/export.xlsx")
def export_excel(job_id: str) -> StreamingResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    output = build_excel(job_id)
    headers = {
        "Content-Disposition": f'attachment; filename="results_{job_id}.xlsx"'
    }
    return StreamingResponse(
        output,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers=headers,
    )


@app.get("/api/jobs/{job_id}/export.md")
def export_markdown(job_id: str) -> Response:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    md = build_markdown(job_id)
    headers = {"Content-Disposition": f'attachment; filename="results_{job_id}.md"'}
    return Response(md, media_type="text/markdown; charset=utf-8", headers=headers)


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
