"""
score_jobs.py
-------------
Scores all status='new' jobs in the DB against the candidate's master CV
using DeepSeek-V3 API (OpenAI-compatible).

Setup:
    pip install openai pymysql
    Set DEEPSEEK_API_KEY env variable or paste it in the config below.

Usage:
    python score_jobs.py
"""

import argparse
import json
import os
import sys
import time
import pymysql
import pymysql.cursors
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEEPSEEK_API_KEY, DB_CONFIG as _DB_BASE

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
BATCH_SIZE = 10
SLEEP_BETWEEN_CALLS = 0.5

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

# ---------------------------------------------------------------------------
# CANDIDATE PROFILE — read from master CV files (single source of truth)
# ---------------------------------------------------------------------------
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
MASTER_CV_PATHS = {
    'crp': _PROJECT_ROOT / 'cv' / 'master' / 'master_cv_crp.md',
    'igm': _PROJECT_ROOT / 'cv' / 'master' / 'master_cv_igm.md',
}
_cv_cache: dict[str, str] = {}

def load_candidate_profile() -> str:
    """Read the igm master CV (superset — has all projects) and return as-is for scoring."""
    if 'profile' not in _cv_cache:
        # Use igm variant as it contains all projects (superset)
        path = MASTER_CV_PATHS['igm']
        with open(path, 'r', encoding='utf-8') as f:
            _cv_cache['profile'] = f.read()
    return _cv_cache['profile']

# ---------------------------------------------------------------------------
# SCORING PROMPT
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a senior technical recruiter scoring job fit for a candidate.
You must return ONLY a valid JSON object — no markdown, no explanation outside JSON.

Scoring rubric:

STEP 1 — Seniority gate (apply first):
| Role type                        | Score ceiling |
| Junior / Trainee                 | 100           |
| Mid / Regular (2–4 yr required)  | 85            |
| Senior (5+ yr required)          | 70            |
| Lead / Principal / Staff         | 45            |
| Head of / Director / Architect   | 25            |

If the JD requires team leadership, mentoring, or owning technical direction as a REQUIREMENT → treat as Lead regardless of title.
A Senior role that just wants solid code with no leadership → ceiling 70.

STEP 2 — Tech fit (within that ceiling):
- All/nearly all musts met → at ceiling
- ~75% musts met → ceiling - 10
- ~50% musts met → ceiling - 20
- <50% musts met → ceiling - 30 or lower
A large must-have list is always a fraction, not additive.

STEP 3 — Adjustments:
- Each genuine nice-to-have met: +3, max +10 total
- Hard blocker (niche platform: HCL Commerce, SAP, COBOL, mainframe, specific ERP) → cap at 25

Final score: clamp to [0, 100].

Sanity checks before scoring:
- Would a hiring manager interview a 2-year junior/mid for this? If clearly no → score < 50
- Title says Lead/Principal/Architect? → score < 50
- JD mentions "team management", "line reports", "own the roadmap"? → score < 50
- Near-perfect tech match for mid role? → score can reach 75–85

The score must reflect REALISTIC interview probability, not keyword overlap.

CV VARIANT — choose which CV version to send:
- "igm" = iGaming/startups variant. Use when the company is in: iGaming, betting, gambling,
  crypto, blockchain, fintech startups, small/medium startups, entertainment tech, or any
  industry where mentioning gaming platforms, crypto payments, and AI projects is a positive.
- "crp" = corporate variant. Use for: banks, insurance, consulting firms (Big4, Accenture, Capgemini),
  large enterprises, government/public sector, traditional corporates, or any company where
  mentioning gambling/crypto could be seen negatively. When in doubt, default to "crp".

Return exactly this JSON and nothing else:
{
  "fit_score": <integer 0-100>,
  "fit_notes": "<Missing: X, Y. One sentence: strongest fit + biggest gap. Max 500 chars.>",
  "cv_variant": "<crp or igm>",
  "cv_variant_confident": <true if clear signal from company/industry, false if defaulting to crp because unsure>
}"""


def make_user_prompt(job: dict) -> str:
    must = job.get('requirements_must') or '[]'
    nice = job.get('requirements_nice') or '[]'
    if isinstance(must, str):
        try:
            must = json.loads(must)
        except Exception:
            must = [must]
    if isinstance(nice, str):
        try:
            nice = json.loads(nice)
        except Exception:
            nice = [nice]

    candidate_profile = load_candidate_profile()

    return f"""Score this job against the candidate profile below.

=== CANDIDATE PROFILE ===
{candidate_profile}

=== JOB ===
Position:   {job.get('position', 'N/A')}
Company:    {job.get('company', 'N/A')}
Seniority:  {job.get('seniority', 'N/A')}
Must-haves: {json.dumps(must, ensure_ascii=False)}
Nice-to-haves: {json.dumps(nice, ensure_ascii=False)}
Job description:
{(job.get('job_description') or '')[:3000]}

Return only the JSON object as instructed."""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
def get_connection():
    return pymysql.connect(**DB_CONFIG)


def posted_within_clause(hours: float | None) -> str:
    if hours is None:
        return ""
    return f" AND posted_at >= DATE(DATE_SUB(NOW(), INTERVAL {hours} HOUR))"


def fetch_batch(conn, posted_hours: float | None = None) -> list:
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, source, position, company, seniority,
                   requirements_must, requirements_nice, job_description
            FROM jobs
            WHERE status = 'new'{posted_within_clause(posted_hours)}
            LIMIT %s
        """, (BATCH_SIZE,))
        return cur.fetchall()


def update_job(conn, job_id: str, source: str, score: int, notes: str, cv_variant: str = 'crp'):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE jobs
            SET fit_score  = %s,
                fit_notes  = %s,
                cv_variant = %s,
                status     = 'scored'
            WHERE id = %s AND source = %s
        """, (score, notes[:500], cv_variant, job_id, source))
    conn.commit()


def verify_update(conn, job_id: str, source: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source, fit_score, fit_notes
            FROM jobs
            WHERE id = %s AND source = %s
        """, (job_id, source))
        return cur.fetchone()


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------
def score_job(client: OpenAI, job: dict) -> tuple[int, str, str]:
    """Call DeepSeek-V3 and return (score, notes, cv_variant). Returns (0, error, 'crp') on failure."""
    prompt = make_user_prompt(job)
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # DeepSeek-V3
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,       # low temp = consistent, deterministic scoring
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        score = int(data.get("fit_score", 0))
        notes = str(data.get("fit_notes", ""))
        cv_variant = str(data.get("cv_variant", "crp")).lower()
        confident = data.get("cv_variant_confident", True)
        if cv_variant not in ('crp', 'igm'):
            cv_variant = 'crp'
            confident = False
        if not confident:
            notes = f"[cv_variant defaulted to crp — unknown company type] {notes}"
        score = max(0, min(100, score))  # clamp
        return score, notes, cv_variant
    except json.JSONDecodeError as e:
        return 0, f"JSON parse error: {e} | raw: {raw[:200]}", 'crp'
    except Exception as e:
        return 0, f"API error: {e}", 'crp'


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Score new jobs')
    parser.add_argument('--posted-within', type=float, default=None,
                        help='Only score jobs posted within this many hours')
    args = parser.parse_args()

    if not DEEPSEEK_API_KEY:
        print("❌  Set DEEPSEEK_API_KEY in .env file")
        return

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )

    conn = get_connection()
    total_scored = 0
    total_errors = 0
    batch_num = 0

    label = f" (posted within {args.posted_within}h)" if args.posted_within else ""
    print(f"🚀  Starting scoring{label}...\n")

    while True:
        batch = fetch_batch(conn, args.posted_within)
        if not batch:
            break

        batch_num += 1
        print(f"── Batch {batch_num} ({len(batch)} jobs) ──────────────────────────")

        for job in batch:
            job_id = job['id']
            source = job['source']
            position = job.get('position', 'N/A')
            company  = job.get('company', 'N/A')

            score, notes, cv_variant = score_job(client, job)

            if notes.startswith("API error") or notes.startswith("JSON parse"):
                total_errors += 1
                print(f"  ❌  [{job_id}] {company} — {position}")
                print(f"       {notes}")
                # Still mark as scored to avoid infinite loop; use score=0 as sentinel
                update_job(conn, job_id, source, 0, notes, cv_variant)
            else:
                update_job(conn, job_id, source, score, notes, cv_variant)
                verified = verify_update(conn, job_id, source)
                total_scored += 1
                bar = "🟢" if score >= 70 else "🟡" if score >= 50 else "🔴"
                print(f"  {bar}  [{score:>3}] {company} — {position} [{cv_variant}]")
                print(f"        {notes[:120]}")
                if not verified or verified['fit_score'] != score:
                    print(f"        ⚠️  Verify failed!")

            time.sleep(SLEEP_BETWEEN_CALLS)

        print()

    # ---------------------------------------------------------------------------
    # Final report
    # ---------------------------------------------------------------------------
    print("=" * 60)
    print(f"✅  Done. Scored: {total_scored}  |  Errors: {total_errors}")
    print("=" * 60)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT (fit_score DIV 10) * 10 AS bucket,
                   COUNT(*) AS count
            FROM jobs
            WHERE fit_score IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket DESC
        """)
        rows = cur.fetchall()
        print("\n📊  Score distribution:")
        for r in rows:
            bar = "█" * r['count']
            print(f"  {r['bucket']:>3}–{r['bucket']+9}:  {bar}  ({r['count']})")

        cur.execute("""
            SELECT id, company, position, fit_score, fit_notes
            FROM jobs
            WHERE fit_score >= 60
            ORDER BY fit_score DESC
            LIMIT 20
        """)
        top = cur.fetchall()
        if top:
            print("\n🏆  Top candidates (score >= 60):")
            for j in top:
                print(f"  [{j['fit_score']:>3}] {j['company']} — {j['position']}")
                print(f"        {(j['fit_notes'] or '')[:100]}")

    conn.close()


if __name__ == "__main__":
    main()
