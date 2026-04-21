import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from db import get_conn
from routers import jobs, actions

POLISH_MARKERS = re.compile(
    r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]'
    r'|(?<!\w)(?:wymagania|doświadczenie|praca|zespół|aplikuj|obowiązki|umiejętności|znajomość'
    r'|wynagrodzenie|oferujemy|oczekujemy|zapewniamy|poszukujemy|stanowisko)(?!\w)',
    re.IGNORECASE,
)

def _detect_language(text: str) -> str:
    if not text:
        return 'en'
    return 'pl' if len(POLISH_MARKERS.findall(text[:3000])) >= 3 else 'en'

def _ensure_language_column():
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE jobs ADD COLUMN language VARCHAR(10) NOT NULL DEFAULT 'en' AFTER job_description")
            conn.commit()
        except Exception:
            return  # column already exists
        cur.execute("SELECT id, source, job_description FROM jobs WHERE language = 'en' AND job_description IS NOT NULL")
        rows = cur.fetchall()
        updated = 0
        for row in rows:
            if _detect_language(row[2]) == 'pl':
                cur.execute("UPDATE jobs SET language = 'pl' WHERE id = %s AND source = %s", (row[0], row[1]))
                updated += 1
        if updated:
            conn.commit()
            print(f'backfill_language: reclassified {updated} job(s) as Polish.')

@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_language_column()
    yield

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(actions.router)
app.include_router(jobs.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
