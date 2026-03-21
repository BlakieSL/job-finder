import asyncio
import sys
import os
import re
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import HTTPException

router = APIRouter()

SCRIPTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
OUTPUT_DIR  = os.path.join(SCRIPTS_DIR, "output_cvs")


async def stream_script(script_name: str, extra_args: list[str] = None):
    cmd = [sys.executable, "-u", script_name] + (extra_args or [])
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=SCRIPTS_DIR,
        env=env,
    )
    try:
        async for line in proc.stdout:
            yield f"data: {line.decode('utf-8', errors='replace').rstrip()}\n\n"
        await proc.wait()
        yield "data: [DONE]\n\n"
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()


@router.post("/actions/scrape")
async def action_scrape():
    return StreamingResponse(stream_script("scrapers/scrape_all.py"), media_type="text/event-stream")

@router.post("/actions/score")
async def action_score():
    return StreamingResponse(stream_script("pipeline/score_jobs.py"), media_type="text/event-stream")

@router.post("/actions/tailor")
async def action_tailor(min_score: int = Query(default=59)):
    return StreamingResponse(
        stream_script("pipeline/tailor_cv.py", ["--min-score", str(min_score)]),
        media_type="text/event-stream"
    )

@router.post("/actions/generate-pdf-batch")
async def action_generate_pdf_batch(min_score: int = Query(default=59)):
    return StreamingResponse(
        stream_script("pipeline/generate_cv.py", ["--batch", "--min-score", str(min_score)]),
        media_type="text/event-stream"
    )

@router.post("/actions/generate-pdf/{job_id}/{source}")
async def action_generate_pdf(job_id: str, source: str):
    return StreamingResponse(
        stream_script("pipeline/generate_cv.py", ["--job-id", job_id]),
        media_type="text/event-stream"
    )

@router.get("/jobs/{job_id}/{source}/pdf")
async def get_job_pdf(job_id: str, source: str):
    safe = re.sub(r'[^\w\-]', '_', job_id)
    pdf_path = os.path.join(OUTPUT_DIR, f"cv_{safe}.pdf")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"cv_{safe}.pdf")

@router.get("/jobs/{job_id}/{source}/pdf-exists")
async def check_job_pdf(job_id: str, source: str):
    safe = re.sub(r'[^\w\-]', '_', job_id)
    pdf_path = os.path.join(OUTPUT_DIR, f"cv_{safe}.pdf")
    return {"exists": os.path.exists(pdf_path)}
