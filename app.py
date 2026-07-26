"""캡컷 에이전트 로컬 웹 서버 (FastAPI + 정적 HTML 1장).

실행:
    uvicorn app:app --reload
그다음 브라우저에서 http://127.0.0.1:8000 접속.
"""
import asyncio
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from capcut_agent.env_check import run_env_check
from capcut_agent.pipeline import run_pipeline

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="캡컷 에이전트")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# faster-whisper(numba)는 스레드 세이프하지 않다 -> 모든 ASR 호출을 이 락으로 직렬화
ASR_LOCK = asyncio.Lock()

JOBS: dict[str, dict] = {}


@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/env")
async def api_env():
    env = run_env_check()
    return {
        "track": env.track,
        "os_name": env.os_name,
        "machine": env.machine,
        "whisper_backend": env.whisper_backend,
        "missing": env.missing,
        "capcut_drafts_dir": env.capcut_drafts_dir,
        "disk_free_gb": round(env.disk_free_gb, 1),
        "ok": env.ok,
    }


@app.post("/api/upload")
async def api_upload(file: UploadFile = File(...)):
    job_id = uuid.uuid4().hex[:12]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "input.mp4").suffix or ".mp4"
    input_path = job_dir / f"input{suffix}"
    with open(input_path, "wb") as f:
        while chunk := await file.read(1 << 20):
            f.write(chunk)

    JOBS[job_id] = {"input_path": str(input_path), "job_dir": str(job_dir)}
    return {
        "job_id": job_id,
        "filename": file.filename,
        "preview_url": f"/uploads/{job_id}/{input_path.name}",
    }


app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/api/events/{job_id}")
async def api_events(
    job_id: str,
    draft_name: str | None = None,
    drafts_dir: str | None = None,
    whisper_model: str = "medium",
    language: str = "ko",
    protected_ranges: str = "[]",
):
    job = JOBS.get(job_id)
    if job is None:
        async def _err():
            yield f"data: {json.dumps({'stage': 'error', 'message': 'job not found'})}\n\n"
        return StreamingResponse(_err(), media_type="text/event-stream")

    env = run_env_check()
    resolved_drafts_dir = drafts_dir or env.capcut_drafts_dir
    resolved_draft_name = draft_name or f"auto_edit_{job_id}"
    try:
        protected = [tuple(r) for r in json.loads(protected_ranges)]
    except (json.JSONDecodeError, TypeError):
        protected = []

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_event(stage: str, payload: dict):
            await queue.put({"stage": stage, **payload})

        async def worker():
            try:
                result = await run_pipeline(
                    job["input_path"],
                    job["job_dir"],
                    resolved_drafts_dir,
                    resolved_draft_name,
                    on_event,
                    ASR_LOCK,
                    whisper_model=whisper_model,
                    language=None if language == "auto" else language,
                    protected_ranges=protected,
                )
                await queue.put({"stage": "complete", **result})
            except Exception as e:  # noqa: BLE001 - SSE로 프론트에 에러를 그대로 전달
                await queue.put({"stage": "error", "message": str(e)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
