from fastapi import APIRouter
from db import get_conn
import json

router = APIRouter()

@router.get("/jobs")
def list_jobs(
    status: str = None,
    source: str = None,
    min_score: int = 0,
    search: str = None
):
    with get_conn() as conn:
        cur = conn.cursor(dictionary=True)
        sql = """
            SELECT id, source, position, company, seniority, salary,
                   fit_score, status, expires_at, scraped_at, url, notes, fit_notes, cv_variant
            FROM jobs WHERE (fit_score >= %s OR fit_score IS NULL)
        """
        params = [min_score]
        if status:
            sql += " AND status = %s"
            params.append(status)
        if source:
            sql += " AND source = %s"
            params.append(source)
        if search:
            sql += " AND (position LIKE %s OR company LIKE %s)"
            params += [f"%{search}%", f"%{search}%"]
        sql += " ORDER BY fit_score DESC"
        cur.execute(sql, params)
        rows = cur.fetchall()
    for row in rows:
        for col in ("expires_at", "scraped_at", "applied_at"):
            if row.get(col) is not None:
                row[col] = str(row[col])
    return rows

@router.get("/jobs/{id}/{source}")
def get_job(id: str, source: str):
    with get_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM jobs WHERE id=%s AND source=%s", (id, source))
        row = cur.fetchone()
    if row:
        for col in ("requirements_must", "requirements_nice", "extra_details"):
            if isinstance(row.get(col), str):
                row[col] = json.loads(row[col])
        for col in ("expires_at", "scraped_at", "applied_at"):
            if row.get(col) is not None:
                row[col] = str(row[col])
    return row

@router.patch("/jobs/{id}/{source}")
def update_job(id: str, source: str, body: dict):
    allowed = {"status", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"ok": False}
    with get_conn() as conn:
        cur = conn.cursor()
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        cur.execute(
            f"UPDATE jobs SET {set_clause} WHERE id=%s AND source=%s",
            list(updates.values()) + [id, source]
        )
        conn.commit()
    return {"ok": True}

@router.get("/stats")
def stats():
    with get_conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT status, COUNT(*) as count FROM jobs GROUP BY status")
        rows = cur.fetchall()
    return {r["status"]: r["count"] for r in rows}
