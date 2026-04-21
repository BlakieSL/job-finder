"""
generate_cv.py — Fill cv_template.html placeholders and render to PDF.

Usage:
    python generate_cv.py --job-id <job_id>

The script:
1. Reads tailored_cv from the DB for the given job_id
2. Parses it into SUMMARY and SKILLS sections
3. Injects into cv_template.html
4. Renders to PDF via headless Chrome
5. Saves as output_cvs/<job_id>.pdf
"""

import argparse
import json
import os
import re
import sys
import base64
import subprocess
import time
import webbrowser
import pymysql
import pymysql.cursors
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG as _DB_BASE

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
TEMPLATE_PATHS = {
    'crp': os.path.join(_PROJECT_ROOT, 'cv', 'templates', 'cv_template_crp.html'),
    'igm': os.path.join(_PROJECT_ROOT, 'cv', 'templates', 'cv_template_igm.html'),
}
OUTPUT_DIR = os.path.join(_PROJECT_ROOT, 'output_cvs')

MASTER_CV_PATHS = {
    'crp': os.path.join(_PROJECT_ROOT, 'cv', 'master', 'master_cv_crp.md'),
    'igm': os.path.join(_PROJECT_ROOT, 'cv', 'master', 'master_cv_igm.md'),
}

_defaults_cache: dict[str, dict] = {}

def _load_defaults(variant: str) -> dict:
    """Parse summary and skills from master CV markdown — cached per variant."""
    if variant in _defaults_cache:
        return _defaults_cache[variant]

    path = MASTER_CV_PATHS.get(variant, MASTER_CV_PATHS['crp'])
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    # Extract summary
    summary_match = re.search(r'## PROFESSIONAL SUMMARY\s*\n(.*?)(?=\n---|\n## |\Z)', text, re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ''

    # Extract skills and convert to HTML
    skills_match = re.search(r'## SKILLS\s*\n(.*?)(?=\n---|\n## |\Z)', text, re.DOTALL)
    skills_html = ''
    if skills_match:
        html_lines = []
        for line in skills_match.group(1).strip().splitlines():
            line = line.strip()
            if not line or ':' not in line:
                continue
            label, rest = line.split(':', 1)
            label_clean = label.strip().strip('*')
            rest_clean = rest.strip().replace('**', '').replace('&', '&amp;')
            html_lines.append(f'<span class="skill-label">{label_clean}:</span> {rest_clean}<br>')
        skills_html = '\n      '.join(html_lines)

    _defaults_cache[variant] = {'summary': summary, 'skills': skills_html}
    return _defaults_cache[variant]


def get_default_summary(variant: str) -> str:
    return _load_defaults(variant)['summary']


def get_default_skills(variant: str) -> str:
    return _load_defaults(variant)['skills']


def parse_tailored_cv(tailored_cv: str, cv_variant: str = 'crp') -> dict:
    """
    Parse the tailored_cv JSON string into title, summary, and skills_html.
    New format (JSON): {"title": "...", "summary": "...", "skills_html": "..."}
    """
    default_summary = get_default_summary(cv_variant)
    default_skills = get_default_skills(cv_variant)
    result = {'title': 'SOFTWARE ENGINEER', 'summary': default_summary, 'skills': default_skills}

    try:
        data = json.loads(tailored_cv)
        if data.get('title'):
            result['title'] = data['title']
        if data.get('summary'):
            result['summary'] = data['summary']
        if data.get('skills_html'):
            result['skills'] = data['skills_html']
        return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Legacy fallback: old markdown format
    summary_match = re.search(r'##\s*SUMMARY\s*\n(.*?)(?=##|\Z)', tailored_cv, re.DOTALL | re.IGNORECASE)
    skills_match = re.search(r'##\s*SKILLS\s*\n(.*?)(?=##|\Z)', tailored_cv, re.DOTALL | re.IGNORECASE)

    if summary_match:
        result['summary'] = summary_match.group(1).strip()

    if skills_match:
        raw_skills = skills_match.group(1).strip()
        html_lines = []
        for line in raw_skills.splitlines():
            line = line.strip()
            if not line:
                continue
            if ':' in line:
                label, rest = line.split(':', 1)
                label_clean = label.strip().strip('*')
                rest_clean = rest.strip().replace('**', '').replace('&', '&amp;')
                html_lines.append(f'<span class="skill-label">{label_clean}:</span> {rest_clean}<br>')
            else:
                rest_clean = line.replace('**', '').replace('&', '&amp;')
                html_lines.append(rest_clean + '<br>')
        if html_lines:
            result['skills'] = '\n      '.join(html_lines)

    return result


def render_pdf(summary: str, skills: str, output_path: str, cv_variant: str = 'crp', title: str = 'SOFTWARE ENGINEER'):
    template_path = TEMPLATE_PATHS.get(cv_variant, TEMPLATE_PATHS['crp'])
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    html = html.replace('{{TITLE}}', title)
    html = html.replace('{{SUMMARY}}', summary)
    html = html.replace('{{SKILLS}}', skills)

    # Write temp filled HTML
    tmp_html = output_path.replace('.pdf', '_tmp.html')
    with open(tmp_html, 'w', encoding='utf-8') as f:
        f.write(html)

    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=opts)

    url = 'file:///' + tmp_html.replace(os.sep, '/')
    driver.get(url)
    time.sleep(2)  # wait for Google Fonts

    pdf_data = driver.execute_cdp_cmd('Page.printToPDF', {
        'printBackground': True,
        'paperWidth': 8.27,
        'paperHeight': 11.69,
        'marginTop': 0,
        'marginBottom': 0,
        'marginLeft': 0,
        'marginRight': 0,
    })
    driver.quit()
    os.remove(tmp_html)

    with open(output_path, 'wb') as f:
        f.write(base64.b64decode(pdf_data['data']))


def mark_pdf_ready(conn, job_id: str, source: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = 'pdf_ready' WHERE id = %s AND source = %s",
            (job_id, source)
        )
    conn.commit()


def posted_within_clause(hours: float | None) -> str:
    if hours is None:
        return ""
    return f" AND posted_at >= DATE(DATE_SUB(NOW(), INTERVAL {hours} HOUR))"


def language_clause(lang: str | None) -> str:
    if lang is None:
        return ""
    return f" AND language = '{lang}'"


def fetch_tailored_jobs(conn, min_score: int, posted_hours: float | None = None, lang: str | None = None) -> list:
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, source, position, company, fit_score, url, tailored_cv, cv_variant
            FROM jobs
            WHERE status = 'tailored' AND fit_score >= %s{posted_within_clause(posted_hours)}{language_clause(lang)}
            ORDER BY fit_score DESC
        """, (min_score,))
        return cur.fetchall()


def fetch_apply_list(conn, min_score: int) -> list:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, source, position, company, fit_score, salary, url
            FROM jobs
            WHERE status = 'pdf_ready' AND fit_score >= %s
            ORDER BY fit_score DESC
        """, (min_score,))
        return cur.fetchall()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id',    required=False, help='Single job ID to generate CV for')
    parser.add_argument('--default',   action='store_true', help='Generate default (non-tailored) CV')
    parser.add_argument('--batch',     action='store_true', help='Generate PDFs for ALL tailored jobs')
    parser.add_argument('--min-score', type=int, default=59, help='Min fit_score for --batch (default: 59)')
    parser.add_argument('--posted-within', type=float, default=None,
                        help='Only generate for jobs posted within this many hours')
    parser.add_argument('--language', type=str, default=None,
                        help='Only generate for jobs in this language (en or pl)')
    parser.add_argument('--list',      action='store_true', help='Print apply list (pdf_ready jobs) without generating')
    parser.add_argument('--open',      action='store_true', help='With --list: open all URLs in browser + open PDF folder')
    parser.add_argument('--variant',   choices=['crp', 'igm'], default='crp',
                        help='CV variant for --default mode (default: crp)')
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Default CV ────────────────────────────────────────────────────────────
    if args.default:
        variant = args.variant
        print(f'Generating default CV [{variant}]...')
        output_path = os.path.join(OUTPUT_DIR, f'cv_default_{variant}.pdf')
        render_pdf(get_default_summary(variant), get_default_skills(variant), output_path, variant)
        print(f'Saved: {output_path}')
        return

    conn = pymysql.connect(**DB_CONFIG)

    # ── Print apply list only ─────────────────────────────────────────────────
    if args.list:
        jobs = fetch_apply_list(conn, args.min_score)
        conn.close()
        if not jobs:
            print(f'No pdf_ready jobs with fit_score >= {args.min_score}. Run --batch first.')
            return
        print(f'\n🎯  Apply list  (fit_score ≥ {args.min_score})  —  {len(jobs)} jobs\n')
        print(f'  {"#":>3}  {"Score":>5}  {"Company":<28}  {"Position":<38}  URL')
        print(f'  {"-"*3}  {"-"*5}  {"-"*28}  {"-"*38}  {"-"*40}')
        for i, job in enumerate(jobs, 1):
            safe = re.sub(r'[^\w\-]', '_', job['id'])
            pdf  = os.path.abspath(os.path.join(OUTPUT_DIR, f'cv_{safe}.pdf'))
            print(f'  {i:>3}  [{job["fit_score"]:>3}]  {(job["company"] or "")[:28]:<28}  {(job["position"] or "")[:38]:<38}  {job["url"]}')
            print(f'       📄 {pdf}')

        if args.open:
            print(f'\n🌐  Opening {len(jobs)} job URLs in browser...')
            for job in jobs:
                webbrowser.open(job['url'])
                time.sleep(0.4)   # slight delay so browser doesn't choke
            print(f'📁  Opening PDF folder...')
            subprocess.Popen(f'explorer "{os.path.abspath(OUTPUT_DIR)}"')
            print('✅  Done — apply away!')
        return

    # ── Batch mode ────────────────────────────────────────────────────────────
    if args.batch:
        jobs = fetch_tailored_jobs(conn, args.min_score, args.posted_within, args.language)
        if not jobs:
            print(f'No tailored jobs with fit_score >= {args.min_score}. Run tailor_cv.py first.')
            conn.close()
            return

        print(f'🖨️   Generating PDFs for {len(jobs)} tailored jobs (score ≥ {args.min_score})...\n')
        done, errors = 0, 0

        for job in jobs:
            job_id     = job['id']
            source     = job['source']
            position   = job.get('position', 'N/A')
            company    = job.get('company',  'N/A')
            score      = job.get('fit_score', 0)
            cv_variant = job.get('cv_variant', 'crp') or 'crp'
            safe       = re.sub(r'[^\w\-]', '_', job_id)
            out_path   = os.path.join(OUTPUT_DIR, f'cv_{safe}.pdf')

            print(f'  [{score:>3}] {company} — {position} [{cv_variant}]')
            try:
                if job['tailored_cv']:
                    parsed  = parse_tailored_cv(job['tailored_cv'], cv_variant)
                    title   = parsed['title']
                    summary = parsed['summary']
                    skills  = parsed['skills']
                else:
                    title   = 'SOFTWARE ENGINEER'
                    summary = get_default_summary(cv_variant)
                    skills  = get_default_skills(cv_variant)

                render_pdf(summary, skills, out_path, cv_variant, title)
                mark_pdf_ready(conn, job_id, source)
                done += 1
                print(f'       ✅  {out_path}')
            except Exception as e:
                errors += 1
                print(f'       ❌  {e}')

        conn.close()

        print(f'\n✅  Done. PDFs generated: {done}  |  Errors: {errors}')
        print(f'\nRun with --list to see your apply queue.\n')
        return

    # ── Single job mode ───────────────────────────────────────────────────────
    if not args.job_id:
        print('Usage: generate_cv.py --job-id <id> | --batch | --default | --list')
        conn.close()
        return

    with conn.cursor() as cur:
        cur.execute(
            'SELECT id, source, position, company, tailored_cv, cv_variant FROM jobs WHERE id = %s',
            (args.job_id,)
        )
        job = cur.fetchone()

    if not job:
        print(f'Job not found: {args.job_id}')
        conn.close()
        return

    cv_variant = job.get('cv_variant', 'crp') or 'crp'

    if not job['tailored_cv']:
        print(f'No tailored_cv for job {args.job_id}, using defaults [{cv_variant}].')
        title   = 'SOFTWARE ENGINEER'
        summary = get_default_summary(cv_variant)
        skills  = get_default_skills(cv_variant)
    else:
        parsed  = parse_tailored_cv(job['tailored_cv'], cv_variant)
        title   = parsed['title']
        summary = parsed['summary']
        skills  = parsed['skills']

    safe_name  = re.sub(r'[^\w\-]', '_', args.job_id)
    output_path = os.path.join(OUTPUT_DIR, f'cv_{safe_name}.pdf')

    print(f'Generating CV for: {job["position"]} @ {job["company"]} [{cv_variant}] title="{title}"')
    render_pdf(summary, skills, output_path, cv_variant, title)
    mark_pdf_ready(conn, args.job_id, job['source'])
    conn.close()
    print(f'Saved: {output_path}')


if __name__ == '__main__':
    main()
