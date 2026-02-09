import json
import re
import time
from typing import Any, Dict, List

import httpx

from .settings import (
    DEFAULT_MODULES,
    MAX_TEXT_CHARS,
    QWEN_API_KEY,
    QWEN_BASE_URL,
    QWEN_MAX_RETRIES,
    QWEN_MODEL,
    QWEN_RETRY_BACKOFF,
    QWEN_TIMEOUT,
)


def _should_retry(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in {429, 500, 502, 503, 504}
    if isinstance(exc, httpx.RequestError):
        return True
    return False


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n...\n{tail}"


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return text


def _extract_json(text: str) -> str:
    text = _strip_code_fences(text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _default_modules(module_defs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"name": m["name"], "score": 0, "comment": ""} for m in module_defs]


def _normalize_result(
    data: Dict[str, Any], module_defs: List[Dict[str, Any]]
) -> Dict[str, Any]:
    modules_in = data.get("modules") if isinstance(data.get("modules"), list) else []
    normalized = {m["name"]: m for m in modules_in if isinstance(m, dict)}

    modules_out = []
    for module in module_defs:
        name = module.get("name", "")
        if not name:
            continue
        item = normalized.get(name, {})
        score = item.get("score")
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        modules_out.append(
            {
                "name": name,
                "score": max(0.0, min(100.0, score)),
                "comment": (item.get("comment") or "").strip(),
            }
        )

    total = data.get("total_score")
    try:
        total = float(total)
    except (TypeError, ValueError):
        if modules_out:
            total = sum(m["score"] for m in modules_out) / len(modules_out)
        else:
            total = 0.0

    return {
        "name": (data.get("name") or "").strip(),
        "phone": (data.get("phone") or "").strip(),
        "email": (data.get("email") or "").strip(),
        "modules": modules_out,
        "total_score": max(0.0, min(100.0, float(total))),
        "summary": (data.get("summary") or "").strip(),
        "raw": data,
    }


def score_resume(
    jd_text: str, resume_text: str, modules: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if not QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY is not set.")

    module_defs = modules or DEFAULT_MODULES
    modules_desc = "\n".join(
        [
            f"- {m['name']}: {m.get('desc', '')}".strip()
            for m in module_defs
            if m.get("name")
        ]
    )

    system_prompt = (
        "You are an HR screening assistant. Evaluate the resume against the JD. "
        "Return ONLY a valid JSON object. No markdown, no extra text. "
        "Use Chinese for summary and comments, keep JSON keys and module names as specified. "
        "Keep technology names (e.g., Vue, Spring Boot) in English."
    )
    user_prompt = (
        "Score the resume using these modules (0-100 each):\n"
        f"{modules_desc}\n\n"
        "Return JSON with this schema:\n"
        "{\n"
        '  "name": "string",\n'
        '  "phone": "string",\n'
        '  "email": "string",\n'
        '  "modules": [\n'
        '    {"name":"SkillMatch","score":0-100,"comment":"string"}\n'
        "  ],\n"
        '  "total_score": 0-100,\n'
        '  "summary": "short evaluation"\n'
        "}\n\n"
        "JD:\n"
        f"{jd_text}\n\n"
        "Resume:\n"
        f"{_truncate_text(resume_text, MAX_TEXT_CHARS)}"
    )

    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }

    headers = {"Authorization": f"Bearer {QWEN_API_KEY}"}
    with httpx.Client(timeout=QWEN_TIMEOUT) as client:
        attempts = max(0, QWEN_MAX_RETRIES) + 1
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = client.post(QWEN_BASE_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1 or not _should_retry(exc):
                    raise
                backoff = max(0.0, QWEN_RETRY_BACKOFF) * (2**attempt)
                time.sleep(backoff)
        if last_exc is not None:
            raise last_exc

    raw_json = _extract_json(content)
    parsed = json.loads(raw_json)
    return _normalize_result(parsed, module_defs)
