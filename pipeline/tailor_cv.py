"""
tailor_cv.py
------------
For every status='scored' AND fit_score >= threshold job in the DB:
  1. Pick job title (LLM — one short string)
  2. Rewrite first sentence of summary to use that title (LLM — one sentence)
  3. Reorder skills to front-load matches (programmatic)
  4. Add genuinely known skills that match requirements (LLM — short list)
  5. Write JSON result to tailored_cv, flip status to 'tailored'

The experience/project bullets are NEVER touched — the hardcore original
content stays as-is. ATS pass comes from title + skills section.

Usage:
    python tailor_cv.py              # process all eligible jobs
    python tailor_cv.py --limit 20   # process at most N jobs
    python tailor_cv.py --min-score 75
"""

import argparse
import json
import os
import re
import sys
import time
import pymysql
import pymysql.cursors
from openai import OpenAI
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DEEPSEEK_API_KEY, DB_CONFIG as _DB_BASE

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
BATCH_SIZE        = 10
SLEEP_BETWEEN_CALLS = 0.7
MIN_SCORE_DEFAULT = 59

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

MASTER_CV_PATHS = {
    'crp': Path(__file__).parent.parent / 'cv' / 'master' / 'master_cv_crp.md',
    'igm': Path(__file__).parent.parent / 'cv' / 'master' / 'master_cv_igm.md',
}
KNOWN_SKILLS_PATH = Path(__file__).parent.parent / 'cv' / 'known_skills.json'

# ---------------------------------------------------------------------------
# MASTER CV — parse skills section from markdown
# ---------------------------------------------------------------------------
_skills_cache: dict[str, list[dict]] = {}

def parse_skills_from_md(variant: str) -> list[dict]:
    """Parse skills section from master CV markdown into list of {label, items}."""
    if variant in _skills_cache:
        return _skills_cache[variant]

    path = MASTER_CV_PATHS.get(variant, MASTER_CV_PATHS['crp'])
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    match = re.search(r'## SKILLS\s*\n(.*?)(?=\n---|\n## |\Z)', text, re.DOTALL)
    if not match:
        _skills_cache[variant] = []
        return []

    skills = []
    for line in match.group(1).strip().splitlines():
        line = line.strip()
        if not line or ':' not in line:
            continue
        label, rest = line.split(':', 1)
        label = label.strip().strip('*')
        rest = rest.strip().lstrip('*').strip()
        items = [s.strip() for s in rest.split(',') if s.strip()]
        skills.append({'label': label, 'items': items})

    _skills_cache[variant] = skills
    return skills


def parse_summary_from_md(variant: str) -> str:
    """Extract the PROFESSIONAL SUMMARY text from master CV."""
    path = MASTER_CV_PATHS.get(variant, MASTER_CV_PATHS['crp'])
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()
    match = re.search(r'## PROFESSIONAL SUMMARY\s*\n(.*?)(?=\n---|\n## |\Z)', text, re.DOTALL)
    return match.group(1).strip() if match else ''


# ---------------------------------------------------------------------------
# SKILLS REORDERING (pure programmatic — no LLM)
# ---------------------------------------------------------------------------
def reorder_skills(skills: list[dict], requirements: list[str]) -> list[dict]:
    """
    Reorder items within each skill group so requirement matches come first.
    Also reorder the groups themselves — groups with more matches go first.
    """
    if not requirements:
        return skills

    req_lower = {r.lower() for r in requirements}
    req_text = ' '.join(req_lower)

    def item_matches(item: str) -> bool:
        item_l = item.lower()
        return item_l in req_lower or any(item_l in r for r in req_lower) or any(r in item_l for r in req_lower)

    reordered = []
    for group in skills:
        matching = [i for i in group['items'] if item_matches(i)]
        rest = [i for i in group['items'] if not item_matches(i)]
        reordered.append({
            'label': group['label'],
            'items': matching + rest,
            '_match_count': len(matching),
        })

    # Sort groups: those with more matches first, but keep Languages always first
    languages = [g for g in reordered if 'language' in g['label'].lower()]
    others = [g for g in reordered if 'language' not in g['label'].lower()]
    others.sort(key=lambda g: g['_match_count'], reverse=True)

    result = languages + others
    for g in result:
        g.pop('_match_count', None)

    return result


def skills_to_html(skills: list[dict]) -> str:
    """Convert skills list to HTML for the template."""
    lines = []
    for group in skills:
        label = group['label']
        items = ', '.join(group['items'])
        lines.append(f'<span class="skill-label">{label}:</span> {items}<br>')
    return '\n      '.join(lines)


# ---------------------------------------------------------------------------
# KNOWN SKILLS — loaded from cv/known_skills.json
# ---------------------------------------------------------------------------
_known_skills: dict | None = None

def load_known_skills() -> dict:
    global _known_skills
    if _known_skills is None:
        with open(KNOWN_SKILLS_PATH, 'r', encoding='utf-8') as f:
            _known_skills = json.load(f)
    return _known_skills


def find_matching_known_skills(requirements: list[str], current_skills: list[dict]) -> list[tuple[str, str]]:
    """
    Find skills from known_skills.json that match job requirements but are
    missing from the current CV skills section. Returns [(skill, group_label)].
    """
    known = load_known_skills()
    never_set = {s.lower() for s in known.get('never', {}).get('items', [])}

    # Flatten current CV skills for dedup
    existing = set()
    for g in current_skills:
        for item in g['items']:
            existing.add(item.lower())

    req_lower = {r.lower() for r in requirements}
    matches = []

    for group_label, items in known.get('safe', {}).items():
        for skill in items:
            skill_l = skill.lower()
            if skill_l in existing:
                continue
            if skill_l in never_set:
                continue
            # Check if this skill matches any requirement
            if skill_l in req_lower or any(skill_l in r for r in req_lower) or any(r in skill_l for r in req_lower):
                matches.append((skill, group_label))

    # Also check "careful" skills — only if explicitly required
    for skill in known.get('careful', {}).get('items', []):
        skill_l = skill.lower()
        if skill_l in existing:
            continue
        if skill_l in req_lower:
            matches.append((skill, '_careful'))

    return matches


def add_matched_skills(skills: list[dict], matched: list[tuple[str, str]]) -> list[dict]:
    """Add matched known skills into the appropriate groups."""
    if not matched:
        return skills

    existing = set()
    for g in skills:
        for item in g['items']:
            existing.add(item.lower())

    # Map known_skills.json group labels to CV group labels
    group_map = {
        'languages': 'languages',
        'backend': 'backend',
        'build tools': 'backend',
        'cloud': 'cloud',
        'devops': 'devops',
        'databases': 'databases',
        'testing': 'testing',
        'observability': 'observability',
        'ai/llm integration': 'backend',
        'frontend': 'frontend',
        'payments': 'backend',
        'security': 'backend',
        'seo & content': 'frontend',
        'design & modelling': 'design',
        'engineering principles': 'methodology',
        'methodology': 'methodology',
        'ides & tools': 'methodology',
        '_careful': 'backend',
    }

    for skill, source_group in matched:
        if skill.lower() in existing:
            continue
        target_key = group_map.get(source_group.lower(), 'backend')
        placed = False
        for g in skills:
            if target_key in g['label'].lower():
                g['items'].append(skill)
                placed = True
                break
        if not placed:
            # Fallback: add to first group
            if skills:
                skills[0]['items'].append(skill)
        existing.add(skill.lower())

    return skills


# ---------------------------------------------------------------------------
# LLM — minimal, structured output only
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are helping tailor a CV for ATS optimisation. You will receive a job posting
and the candidate's current summary. Return ONLY a JSON object with these fields:

1. "title" — The best CV title for this specific job. Keep it short (2-4 words). Always uppercase.
   CRITICAL RULE: NEVER include seniority prefixes like "Junior", "Mid", "Senior", "Lead", "Trainee"
   in the title. The candidate presents as a general-level professional — seniority labels limit them.
   Good: "SOFTWARE ENGINEER", "JAVA DEVELOPER", "BACKEND DEVELOPER", "FULL STACK ENGINEER".
   Bad: "JUNIOR JAVA DEVELOPER", "MID SOFTWARE ENGINEER", "SENIOR BACKEND DEVELOPER".
   You MAY change the specialization to match the job (e.g. "Java Developer" → "Backend Developer"
   or "Cloud Engineer") but NEVER add or change seniority level.

2. "first_sentence" — Rewrite ONLY the first sentence of the candidate's professional summary
   to open with the job title and weave in 2-3 of the most important requirements naturally.
   Keep the same assertive, quantified tone as the original. This replaces ONLY sentence 1.
   CRITICAL RULES:
   - NEVER mention the company name. The CV must be company-neutral.
     Bad: "...seeking to contribute at COMARCH" or "...to join Revolut's team".
   - ONLY mention technologies/skills from the candidate's ACTUAL SKILLS LIST provided below.
     Do NOT invent or add skills the candidate doesn't have. If a job requires Angular but the
     candidate doesn't list it, do NOT mention Angular in the summary.
   - Focus on the candidate's REAL strengths that overlap with the job requirements.

Return ONLY valid JSON, no markdown, no explanation."""


def llm_tailor(client: OpenAI, job: dict, current_summary: str, variant: str = 'crp') -> tuple[dict, str]:
    """
    Ask LLM for title and first_sentence only.
    Returns (result_dict, error_string). On failure: ({}, error).
    """
    must = job.get('requirements_must') or '[]'
    nice = job.get('requirements_nice') or '[]'
    if isinstance(must, str):
        try: must = json.loads(must)
        except: must = [must]
    if isinstance(nice, str):
        try: nice = json.loads(nice)
        except: nice = [nice]

    skills = parse_skills_from_md(variant)
    all_skills = [item for group in skills for item in group['items']]

    prompt = f"""Job posting:
Position: {job.get('position', 'N/A')}
Company: {job.get('company', 'N/A')}
Seniority: {job.get('seniority', 'N/A')}
Must-haves: {json.dumps(must, ensure_ascii=False)}
Nice-to-haves: {json.dumps(nice, ensure_ascii=False)}
Description (first 2000 chars):
{(job.get('job_description') or '')[:2000]}

Candidate's current professional summary:
{current_summary}

Candidate's ACTUAL skills (only mention these in first_sentence):
{', '.join(all_skills)}

Return the JSON object with "title" and "first_sentence"."""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        title = str(data.get('title', 'SOFTWARE ENGINEER')).upper().strip()
        title = re.sub(r'^(JUNIOR|MID|MID-LEVEL|MIDDLE|SENIOR|LEAD|PRINCIPAL|TRAINEE|INTERN)\s+', '', title)
        first_sentence = str(data.get('first_sentence', '')).strip()

        return {'title': title, 'first_sentence': first_sentence}, ''
    except json.JSONDecodeError as e:
        return {}, f"JSON parse error: {e}"
    except Exception as e:
        return {}, f"API error: {e}"


# ---------------------------------------------------------------------------
# ASSEMBLE TAILORED OUTPUT
# ---------------------------------------------------------------------------
def build_tailored_json(variant: str, llm_result: dict, requirements: list[str]) -> tuple[str, list]:
    """
    Build the tailored CV data as JSON string with: title, summary, skills_html.
    Returns (json_string, added_skills_list).
    """
    import copy

    # Summary: replace first sentence, keep the rest
    original_summary = parse_summary_from_md(variant)
    first_sentence = llm_result.get('first_sentence', '')

    if first_sentence and original_summary:
        # Split on first period followed by space or end
        parts = re.split(r'(?<=\.)\s+', original_summary, maxsplit=1)
        if len(parts) > 1:
            summary = first_sentence.rstrip('.') + '. ' + parts[1]
        else:
            summary = first_sentence
    else:
        summary = original_summary

    # Skills: parse from master CV, find matching known skills, add them, reorder
    skills = copy.deepcopy(parse_skills_from_md(variant))
    matched = find_matching_known_skills(requirements, skills)
    added_names = [s for s, _ in matched]
    skills = add_matched_skills(skills, matched)
    skills = reorder_skills(skills, requirements)
    skills_html = skills_to_html(skills)

    title = llm_result.get('title', 'SOFTWARE ENGINEER')

    result = {
        'title': title,
        'summary': summary,
        'skills_html': skills_html,
    }

    return json.dumps(result, ensure_ascii=False), added_names


# ---------------------------------------------------------------------------
# DB HELPERS
# ---------------------------------------------------------------------------
def get_connection():
    return pymysql.connect(**DB_CONFIG)


def posted_within_clause(hours: float | None) -> str:
    if hours is None:
        return ""
    return f" AND posted_at >= DATE(DATE_SUB(NOW(), INTERVAL {hours} HOUR))"


def fetch_batch(conn, min_score: int, posted_hours: float | None = None) -> list:
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, source, position, company, seniority,
                   requirements_must, requirements_nice, job_description,
                   fit_score, fit_notes, cv_variant
            FROM jobs
            WHERE status = 'scored' AND fit_score >= %s{posted_within_clause(posted_hours)}
            ORDER BY fit_score DESC
            LIMIT %s
        """, (min_score, BATCH_SIZE))
        return cur.fetchall()


def fetch_single(conn, job_id: str) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source, position, company, seniority,
                   requirements_must, requirements_nice, job_description,
                   fit_score, fit_notes, cv_variant
            FROM jobs
            WHERE id = %s
        """, (job_id,))
        return cur.fetchall()


def update_job(conn, job_id: str, source: str, tailored_cv: str):
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE jobs
            SET tailored_cv = %s,
                status      = 'tailored'
            WHERE id = %s AND source = %s
        """, (tailored_cv, job_id, source))
    conn.commit()


def verify_update(conn, job_id: str, source: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source, status, LEFT(tailored_cv, 80) AS preview
            FROM jobs
            WHERE id = %s AND source = %s
        """, (job_id, source))
        return cur.fetchone()


def count_remaining(conn, min_score: int, posted_hours: float | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT COUNT(*) AS cnt
            FROM jobs
            WHERE status = 'scored' AND fit_score >= %s{posted_within_clause(posted_hours)}
        """, (min_score,))
        row = cur.fetchone()
        return row['cnt'] if row else 0


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Tailor CVs for scored jobs')
    parser.add_argument('--limit',     type=int, default=None, help='Max number of jobs to process')
    parser.add_argument('--min-score', type=int, default=MIN_SCORE_DEFAULT,
                        help=f'Minimum fit_score to tailor (default: {MIN_SCORE_DEFAULT})')
    parser.add_argument('--posted-within', type=float, default=None,
                        help='Only tailor jobs posted within this many hours')
    parser.add_argument('--job-id', type=str, default=None,
                        help='Tailor CV for a single job by ID')
    args = parser.parse_args()

    client = OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
    )

    conn = get_connection()

    if args.job_id:
        batch = fetch_single(conn, args.job_id)
        if not batch:
            print(f"❌  Job '{args.job_id}' not found")
            conn.close()
            return
        job = batch[0]
        score = job.get('fit_score', 0)
        cv_variant = job.get('cv_variant', 'crp') or 'crp'
        position = job.get('position', 'N/A')
        company = job.get('company', 'N/A')
        print(f"🚀  Tailoring single job: [{score}] {company} — {position} [{cv_variant}]\n")

        must_raw = job.get('requirements_must') or '[]'
        if isinstance(must_raw, str):
            try: requirements = json.loads(must_raw)
            except: requirements = [must_raw]
        else:
            requirements = must_raw or []

        summary = parse_summary_from_md(cv_variant)
        llm_result, error = llm_tailor(client, job, summary, cv_variant)
        if error:
            print(f"  ❌  {error}")
            update_job(conn, job['id'], job['source'], json.dumps({'error': error}))
        else:
            tailored_json, added_skills = build_tailored_json(cv_variant, llm_result, requirements)
            update_job(conn, job['id'], job['source'], tailored_json)
            title = llm_result.get('title', '?')
            print(f'  ✅  title: "{title}" | +skills: {added_skills if added_skills else "none"}')
        print(f"\n✅  Done.")
        conn.close()
        return

    remaining = count_remaining(conn, args.min_score, args.posted_within)
    print(f'🎯  Jobs eligible (scored, fit_score >= {args.min_score}): {remaining}')
    if args.limit:
        print(f'    Processing at most: {args.limit}')
    print()

    if remaining == 0:
        print('✅  Nothing to tailor.')
        conn.close()
        return

    total_tailored = 0
    total_errors   = 0
    batch_num      = 0
    report_rows    = []

    print('🚀  Starting tailoring...\n')

    while True:
        if args.limit and total_tailored + total_errors >= args.limit:
            break

        batch = fetch_batch(conn, args.min_score, args.posted_within)
        if not batch:
            break

        batch_num += 1
        print(f'── Batch {batch_num} ({len(batch)} jobs) ──────────────────────────')

        for job in batch:
            if args.limit and total_tailored + total_errors >= args.limit:
                break

            job_id     = job['id']
            source     = job['source']
            position   = job.get('position', 'N/A')
            company    = job.get('company',  'N/A')
            score      = job.get('fit_score', 0)
            cv_variant = job.get('cv_variant', 'crp') or 'crp'

            # Parse requirements
            must_raw = job.get('requirements_must') or '[]'
            if isinstance(must_raw, str):
                try: requirements = json.loads(must_raw)
                except: requirements = [must_raw]
            else:
                requirements = must_raw or []

            print(f'  ✍️   [{score:>3}] {company} — {position} [{cv_variant}]')

            # Get LLM decisions (title, first sentence, extra skills)
            summary = parse_summary_from_md(cv_variant)
            llm_result, error = llm_tailor(client, job, summary, cv_variant)

            if error:
                total_errors += 1
                print(f'       ❌  {error}')
                update_job(conn, job_id, source, json.dumps({'error': error}))
                report_rows.append((score, company, position, 'error ✗'))
            else:
                # Build tailored data
                tailored_json, added_skills = build_tailored_json(cv_variant, llm_result, requirements)
                update_job(conn, job_id, source, tailored_json)
                verified = verify_update(conn, job_id, source)

                title = llm_result.get('title', '?')

                if verified and verified['status'] == 'tailored':
                    total_tailored += 1
                    print(f'       ✅  title: "{title}" | +skills: {added_skills if added_skills else "none"}')
                    report_rows.append((score, company, position, 'tailored ✓'))
                else:
                    total_errors += 1
                    print(f'       ⚠️   DB verify failed!')
                    report_rows.append((score, company, position, 'verify failed ✗'))

            time.sleep(SLEEP_BETWEEN_CALLS)

        print()

    # Final report
    print('=' * 70)
    print(f'✅  Done.  Tailored: {total_tailored}  |  Errors: {total_errors}')
    print('=' * 70)

    if report_rows:
        print('\n📋  Summary:\n')
        print(f'  {"#":>3}  {"Score":>5}  {"Company":<25}  {"Position":<35}  Status')
        print(f'  {"-"*3}  {"-"*5}  {"-"*25}  {"-"*35}  {"-"*14}')
        for i, (score, company, position, status) in enumerate(report_rows, 1):
            print(f'  {i:>3}  [{score:>3}]  {company[:25]:<25}  {position[:35]:<35}  {status}')

    conn.close()
    print()


if __name__ == '__main__':
    main()
