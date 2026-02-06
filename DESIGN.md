# 简历筛选平台设计文档

## 1. 目标与范围
面向部门 HR 的简历筛选工具，支持一次上传最多 100 份 PDF 简历并录入 JD，调用 Qwen3 大模型评分，输出按总分排序的综合表（Excel/Markdown），包含姓名、联系方式、各模块评分与评价。

## 2. 核心功能
- JD 输入 + 批量 PDF 简历上传（<=100）
- 异步评分队列，实时进度展示
- 结果列表按总分排序
- 导出 Excel 与 Markdown 总表
- 模块化评分与点评（中文输出，技术名词保留英文）

## 3. 系统架构
- 前端：静态页面（HTML/CSS/JS），调用后端 API。
- 后端：FastAPI + SQLite + 本地任务队列线程。
- 模型：Qwen3（qwen3-max），兼容 OpenAI Chat Completions 接口。

```
Browser (SPA)
  └─ /api/upload      ──> FastAPI
  └─ /api/jobs/...    ──> FastAPI ──> SQLite
                       └─ Worker Queue ──> Qwen3 API
```

## 4. 模块与职责
- `backend/main.py`
  - API 路由
  - 任务队列与 worker
  - 静态文件挂载
- `backend/qwen.py`
  - 模型请求与 JSON 解析
  - 结构化评分输出
- `backend/utils.py`
  - PDF 文本抽取
  - 联系方式补全
- `backend/db.py`
  - SQLite CRUD
- `backend/report.py`
  - Excel/Markdown 导出
- `web/*`
  - 前端页面与交互

## 5. 数据流
1. 前端提交 JD + PDFs 到 `/api/upload`
2. 后端存储文件、创建任务记录（状态 queued）
3. Worker 读取 PDF，调用 Qwen3 评分
4. 写入评分、总评与联系方式
5. 前端轮询 `/api/jobs/{job_id}/status` 和 `/api/jobs/{job_id}/results`
6. 导出 `/api/jobs/{job_id}/export.xlsx` 或 `.md`

## 6. 评分设计
### 模块（可配置）
- 技能匹配（SkillMatch）
- 项目经验（ProjectExperience）
- 工作年限（YearsExperience）
- 教育背景（Education）
- 协作沟通（Collaboration）
- 稳定性（Stability）

### 输出格式（JSON）
```
{
  "name": "string",
  "phone": "string",
  "email": "string",
  "modules": [
    {"name":"SkillMatch","score":0-100,"comment":"string"}
  ],
  "total_score": 0-100,
  "summary": "string"
}
```
要求：`summary/comment` 为中文；技术名词（如 Vue、Spring Boot）保持英文。

## 7. 数据模型（SQLite）
**jobs**
- id (TEXT, PK)
- jd_text (TEXT)
- created_at (TEXT)

**resumes**
- id (TEXT, PK)
- job_id (TEXT, FK)
- file_name (TEXT)
- file_path (TEXT)
- status (TEXT) queued/processing/done/error
- name, phone, email (TEXT)
- total_score (REAL)
- modules_json (TEXT)
- summary (TEXT)
- raw_json (TEXT)
- error (TEXT)
- created_at, updated_at (TEXT)

## 8. API 设计
- `POST /api/upload`
  - form: `jd`, `files[]`
  - 返回：`{ job_id, count }`

- `GET /api/jobs/{job_id}/status`
  - 返回队列状态统计

- `GET /api/jobs/{job_id}/results`
  - 返回所有结果（按总分排序）

- `GET /api/jobs/{job_id}/export.xlsx`
- `GET /api/jobs/{job_id}/export.md`

## 9. 前端页面
- JD 输入区域
- PDF 拖拽上传
- 状态面板（排队、处理中、完成、错误）
- 结果表格（中文列头、模块评分、总评）
- 导出按钮（Excel/Markdown）

## 10. 配置与运行
- `.env`：
  - `QWEN_API_KEY`
  - `QWEN_MODEL=qwen3-max`
  - `QWEN_BASE_URL`
  - `MAX_FILES`
  - `MAX_TEXT_CHARS`

- 启动：
  ```
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
  ```

## 11. 安全与隐私
- 不在前端暴露 API Key
- 本地文件存储，数据库与上传目录不对外暴露
- 限制上传数量与 PDF 类型

## 12. 性能与限制
- 同步线程队列（单进程），适合小批量（<=100）
- PDF 文字提取耗时与模型请求为主要瓶颈
- 可扩展为 Celery/Redis 以支持更大并发

## 13. 未来优化
- 多 Job 管理列表
- 评分模块可配置
- 失败任务重试
- 结果二次筛选与打标签
- 支持 DOCX
