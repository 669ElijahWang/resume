import json
import queue
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .db import (
    count_resumes,
    create_job,
    create_profile,
    create_resume,
    delete_profile,
    get_job,
    get_profile,
    get_resume,
    init_db,
    list_resumes,
    list_profiles,
    update_resume,
    update_profile,
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


def _parse_profile_row(row: Dict[str, Any]) -> Dict[str, Any]:
    modules = []
    rules = []
    try:
        modules = json.loads(row.get("modules_json") or "[]")
    except json.JSONDecodeError:
        modules = []
    try:
        rules = json.loads(row.get("rules_json") or "[]")
    except json.JSONDecodeError:
        rules = []
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "version": row.get("version"),
        "modules": modules,
        "rules": rules,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_modules(raw_modules: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_modules, list):
        raise HTTPException(status_code=400, detail="modules must be a list.")

    modules: List[Dict[str, Any]] = []
    for item in raw_modules:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        label = (item.get("label") or name).strip()
        desc = (item.get("desc") or "").strip()
        weight = item.get("weight")
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 0.0
        must_have = bool(item.get("must_have")) if "must_have" in item else False
        threshold = item.get("threshold")
        try:
            threshold = float(threshold) if threshold is not None else None
        except (TypeError, ValueError):
            threshold = None
        modules.append(
            {
                "name": name,
                "label": label,
                "desc": desc,
                "weight": max(0.0, weight),
                "must_have": must_have,
                "threshold": threshold,
            }
        )

    if not modules:
        raise HTTPException(status_code=400, detail="modules cannot be empty.")

    total = sum(m["weight"] for m in modules)
    if total <= 0:
        weight = 1.0 / len(modules)
        for module in modules:
            module["weight"] = weight
    else:
        for module in modules:
            module["weight"] = module["weight"] / total

    return modules


def _normalize_rules(raw_rules: Any) -> List[Dict[str, Any]]:
    if raw_rules is None:
        return []
    if not isinstance(raw_rules, list):
        raise HTTPException(status_code=400, detail="rules must be a list.")
    return [r for r in raw_rules if isinstance(r, dict)]


def _weights_for_modules(
    profile_modules: List[Dict[str, Any]], module_names: List[str]
) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    total = 0.0
    for module in profile_modules:
        name = module.get("name")
        if not name:
            continue
        weight = module.get("weight")
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            weight = 0.0
        weight = max(0.0, weight)
        weights[name] = weight
        total += weight

    if not module_names:
        return {}

    if total <= 0:
        equal = 1.0 / len(module_names)
        return {name: equal for name in module_names}

    return {name: weights.get(name, 0.0) / total for name in module_names}


def _calculate_total_score(
    scored_modules: List[Dict[str, Any]], profile_modules: List[Dict[str, Any]]
) -> float:
    names = [m.get("name", "") for m in scored_modules if m.get("name")]
    weights = _weights_for_modules(profile_modules, names)
    total = 0.0
    for module in scored_modules:
        name = module.get("name")
        if not name:
            continue
        score = module.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        total += score * weights.get(name, 0.0)
    return max(0.0, min(100.0, total))


def _apply_module_rules(
    scored_modules: List[Dict[str, Any]], profile_modules: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    module_defs: Dict[str, Dict[str, Any]] = {}
    for module in profile_modules:
        name = module.get("name")
        if not name:
            continue
        module_defs[name] = module

    adjusted: List[Dict[str, Any]] = []
    for module in scored_modules:
        name = module.get("name")
        score = module.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0

        definition = module_defs.get(name, {})
        must_have = bool(definition.get("must_have")) if definition else False
        threshold = definition.get("threshold") if definition else None
        if threshold in ("", None):
            threshold = 60.0 if must_have else None
        try:
            threshold = float(threshold) if threshold is not None else None
        except (TypeError, ValueError):
            threshold = 60.0 if must_have else None

        if threshold is not None and score < threshold:
            score = 0.0

        adjusted.append(
            {
                "name": name,
                "score": max(0.0, min(100.0, score)),
                "comment": module.get("comment") or "",
            }
        )

    return adjusted


def _load_job_profile(job: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw = job.get("profile_json") if job else None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _fallback_profile_modules() -> List[Dict[str, Any]]:
    modules: List[Dict[str, Any]] = []
    if not DEFAULT_MODULES:
        return modules
    weight = 1.0 / len(DEFAULT_MODULES)
    for module in DEFAULT_MODULES:
        name = module.get("name", "")
        modules.append(
            {
                "name": name,
                "label": name,
                "desc": module.get("desc", ""),
                "weight": weight,
                "must_have": False,
                "threshold": None,
            }
        )
    return modules


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
        profile = _load_job_profile(job) or {}
        profile_modules = profile.get("modules") if isinstance(profile.get("modules"), list) else []
        if not profile_modules:
            profile_modules = _fallback_profile_modules()

        result = score_resume(job["jd_text"], text, profile_modules)
        scored_modules = _apply_module_rules(
            result.get("modules", []), profile_modules
        )
        total_score = _calculate_total_score(scored_modules, profile_modules)
        contact = backfill_contact(result, text, resume["file_name"])
        update_resume(
            resume_id,
            {
                "status": "done",
                "name": contact["name"] or result.get("name", ""),
                "phone": contact["phone"] or result.get("phone", ""),
                "email": contact["email"] or result.get("email", ""),
                "total_score": total_score,
                "modules_json": json.dumps(scored_modules, ensure_ascii=False),
                "summary": result.get("summary", ""),
                "raw_json": json.dumps(result.get("raw", {}), ensure_ascii=False),
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


@app.get("/api/score-profiles")
def score_profiles() -> JSONResponse:
    profiles = list_profiles()
    items = [_parse_profile_row(p) for p in profiles]
    return JSONResponse({"items": items})


@app.get("/api/score-profiles/{profile_id}")
def score_profile_detail(profile_id: str) -> JSONResponse:
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="评分标准不存在。")
    return JSONResponse(_parse_profile_row(profile))


@app.post("/api/score-profiles")
def create_score_profile(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required.")

    modules = _normalize_modules(payload.get("modules"))
    rules = _normalize_rules(payload.get("rules"))
    version = payload.get("version") or 1
    try:
        version = int(version)
    except (TypeError, ValueError):
        version = 1
    profile_id = payload.get("id") or uuid.uuid4().hex

    create_profile(profile_id, name, version, modules, rules)
    return JSONResponse({"id": profile_id})


@app.put("/api/score-profiles/{profile_id}")
def update_score_profile(
    profile_id: str, payload: Dict[str, Any] = Body(...)
) -> JSONResponse:
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="评分标准不存在。")

    fields: Dict[str, Any] = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name cannot be empty.")
        fields["name"] = name

    if "modules" in payload:
        fields["modules"] = _normalize_modules(payload.get("modules"))

    if "rules" in payload:
        fields["rules"] = _normalize_rules(payload.get("rules"))

    if "version" in payload:
        try:
            fields["version"] = int(payload.get("version"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="version must be an integer.")

    if not fields:
        return JSONResponse({"ok": True})

    update_profile(profile_id, fields)
    return JSONResponse({"ok": True})


@app.delete("/api/score-profiles/{profile_id}")
def delete_score_profile(profile_id: str) -> JSONResponse:
    if profile_id == "default":
        raise HTTPException(status_code=400, detail="默认评分标准不能删除。")
    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="评分标准不存在。")
    delete_profile(profile_id)
    return JSONResponse({"ok": True})


@app.post("/api/upload")
async def upload_resumes(
    jd: str = Form(...),
    profile_id: str = Form("default"),
    files: List[UploadFile] = File(...),
) -> JSONResponse:
    if not jd.strip():
        raise HTTPException(status_code=400, detail="请填写 JD。")
    if not files:
        raise HTTPException(status_code=400, detail="请上传 PDF 文件。")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"最多上传 {MAX_FILES} 份简历。")

    profile = get_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="评分标准不存在。")

    job_id = uuid.uuid4().hex
    profile_snapshot = _parse_profile_row(profile)
    create_job(
        job_id,
        jd.strip(),
        profile_id=profile_id,
        profile_json=json.dumps(profile_snapshot, ensure_ascii=False),
    )
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
    profile = _load_job_profile(job) or {}
    profile_modules = (
        profile.get("modules") if isinstance(profile.get("modules"), list) else []
    )
    if not profile_modules:
        profile_modules = _fallback_profile_modules()

    module_meta = []
    for module in profile_modules:
        name = module.get("name", "")
        if not name:
            continue
        label = module.get("label") or name
        module_meta.append({"name": name, "label": label})

    return JSONResponse(
        {
            "job_id": job_id,
            "modules": module_meta,
            "profile": {
                "id": profile.get("id"),
                "name": profile.get("name"),
                "version": profile.get("version"),
            },
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
