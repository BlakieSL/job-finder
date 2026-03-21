import re
import json
import os
import sys
import time
import requests
import pymysql
import pymysql.cursors
from datetime import date, datetime
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG as _DB_BASE

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

SOURCE = 'justjoinit'

HEADERS = {
    'x-api-version': '1',
    'accept': 'application/json, text/plain, */*',
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
}

LIST_URL = 'https://justjoin.it/api/candidate-api/offers'
DETAIL_URL = 'https://justjoin.it/api/candidate-api/offers/{slug}'
JOB_URL = 'https://justjoin.it/job-offer/{slug}'




def get_connection():
    return pymysql.connect(**DB_CONFIG)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_salary(employment_types: list) -> str:
    """Format salary from employmentTypes. Only original-currency entries included."""
    parts = []
    for et in employment_types:
        if et.get('currencySource') != 'original':
            continue
        rate_from = et['from'] if et.get('from') is not None else et.get('fromPerUnit')
        rate_to = et['to'] if et.get('to') is not None else et.get('toPerUnit')
        if rate_from is None:
            continue
        currency = et.get('currency', '')
        unit = et.get('unit', '')
        contract = et.get('type', '')
        gross = ' gross' if et.get('gross') else ''
        if rate_to and rate_to != rate_from:
            rate_str = f"{int(float(rate_from))}\u2013{int(float(rate_to))}"
        else:
            rate_str = str(int(float(rate_from)))
        parts.append(f"{contract} {rate_str} {currency} {unit}{gross}".strip())
    return ' | '.join(parts) if parts else 'Not disclosed'


def strip_html(html: str) -> str:
    """Strip HTML tags from job body, preserving structure with newlines."""
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup.find_all(['p', 'li', 'br', 'h1', 'h2', 'h3', 'h4']):
        tag.insert_before('\n')
    text = soup.get_text(separator='', strip=False)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def fetch_offers_page(from_cursor: int = 0, items_count: int = 100) -> dict:
    """Fetch one page of offer listings. Returns raw API response dict."""
    params = [
        ('categories', 'java'),
        ('city', 'Warszawa'),
        ('cityRadius', '30'),
        ('remoteWorkOptions', 'hybrid'),
        ('remoteWorkOptions', 'office'),
        ('remoteWorkOptions', 'remote'),
        ('currency', 'pln'),
        ('experienceLevels', 'junior'),
        ('experienceLevels', 'mid'),
        # senior/c_level excluded — API confirmed every JJI job has seniority set,
        # so no untagged junior/mid jobs are missed by this filter.
        ('from', from_cursor),
        ('itemsCount', items_count),
        ('orderBy', 'descending'),
        ('sortBy', 'publishedAt'),
        ('keywordType', 'any'),
    ]
    response = requests.get(LIST_URL, headers=HEADERS, params=params)
    response.raise_for_status()
    return response.json()


def fetch_offer_detail(slug: str) -> dict:
    """Fetch full offer detail including body HTML."""
    url = DETAIL_URL.format(slug=slug)
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Mapping & DB
# ---------------------------------------------------------------------------

def map_job(offer: dict, detail: dict) -> dict:
    """Combine list offer + detail response into a DB-ready dict."""
    slug = offer['slug']

    expires_at = None
    raw_expires = offer.get('expiredAt') or detail.get('expiredAt', '')
    if raw_expires:
        try:
            expires_at = datetime.fromisoformat(raw_expires.replace('Z', '+00:00')).date()
        except ValueError:
            pass

    extra_details = {
        'workplaceType': offer.get('workplaceType'),
        'workingTime': offer.get('workingTime'),
        'city': offer.get('city'),
        'companySize': detail.get('companySize'),
        'languages': detail.get('languages', []),
        'remoteInterview': detail.get('isRemoteInterview'),
    }
    extra_details = {k: v for k, v in extra_details.items() if v is not None}

    raw_seniority = (offer.get('experienceLevel') or '').strip()
    seniority = ', '.join(w.capitalize() for w in raw_seniority.split(','))

    return {
        'id': slug,
        'position': offer.get('title'),
        'company': offer.get('companyName'),
        'seniority': seniority or None,
        'salary': format_salary(offer.get('employmentTypes', [])),
        'expires_at': expires_at,
        'requirements_must': [s['name'] for s in offer.get('requiredSkills', [])],
        'requirements_nice': [s['name'] for s in offer.get('niceToHaveSkills', [])],
        'extra_details': extra_details,
        'job_description': strip_html(detail.get('body', '')),
        'url': JOB_URL.format(slug=slug),
    }


def upsert_job(conn, job: dict) -> bool:
    """Insert job, skip if URL already exists. Returns True if inserted."""
    with conn.cursor() as cur:
        rows = cur.execute("""
            INSERT IGNORE INTO jobs
                (id, source, position, company, seniority, salary,
                 expires_at, scraped_at, requirements_must, requirements_nice,
                 extra_details, job_description, url)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s,
                 %s, %s, %s)
        """, (
            job['id'],
            SOURCE,
            job.get('position'),
            job.get('company'),
            job.get('seniority'),
            job.get('salary'),
            job.get('expires_at'),
            date.today(),
            json.dumps(job.get('requirements_must', []), ensure_ascii=False),
            json.dumps(job.get('requirements_nice', []), ensure_ascii=False),
            json.dumps(job.get('extra_details', {}), ensure_ascii=False),
            job.get('job_description'),
            job['url'],
        ))
    conn.commit()
    return rows == 1


def ensure_schema(conn):
    """Reuse existing jobs table — no schema changes needed."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id                  VARCHAR(255)    NOT NULL,
                source              VARCHAR(50)     NOT NULL,
                position            VARCHAR(255),
                company             VARCHAR(255),
                seniority           VARCHAR(100),
                salary              VARCHAR(500),
                expires_at          DATE,
                scraped_at          DATE            NOT NULL,
                requirements_must   JSON,
                requirements_nice   JSON,
                extra_details       JSON,
                job_description     TEXT,
                status              VARCHAR(50)     NOT NULL DEFAULT 'new',
                tailored_cv         TEXT,
                applied_at          DATE,
                notes               TEXT,
                url                 VARCHAR(500)    NOT NULL,
                PRIMARY KEY (id, source),
                UNIQUE KEY uq_url (url)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        migrations = [
            "ALTER TABLE jobs ADD COLUMN fit_score TINYINT UNSIGNED DEFAULT NULL AFTER status",
            "ALTER TABLE jobs ADD COLUMN fit_notes VARCHAR(500) DEFAULT NULL AFTER fit_score",
        ]
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception:
                pass
    conn.commit()


def normalize_seniority_case(conn):
    """Capitalize the first letter of every seniority word in the DB.

    Examples:
        'senior'        -> 'Senior'
        'mid junior'    -> 'Mid, Junior'
        'SENIOR, MID'   -> 'Senior, Mid'
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, source, seniority FROM jobs WHERE seniority IS NOT NULL")
        rows = cur.fetchall()
        updated = 0
        for row in rows:
            raw = row['seniority']
            tokens = [t.strip() for t in re.split(r'[,\s]+', raw) if t.strip()]
            normalized = ', '.join(t.capitalize() for t in tokens)
            if normalized != raw:
                cur.execute(
                    "UPDATE jobs SET seniority = %s WHERE id = %s AND source = %s",
                    (normalized, row['id'], row['source']),
                )
                updated += 1
    conn.commit()
    print(f'normalize_seniority_case: updated {updated} row(s).')


def remove_seniors(conn):
    """Delete all jobs where seniority contains 'Senior' (case-insensitive)."""
    with conn.cursor() as cur:
        affected = cur.execute(
            "DELETE FROM jobs WHERE LOWER(seniority) LIKE '%senior%'"
        )
    conn.commit()
    print(f'remove_seniors: deleted {affected} row(s).')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(limit: int = None):
    print('Connecting to MySQL...')
    conn = get_connection()
    ensure_schema(conn)
    print('Connected. Schema ready.')

    inserted = 0
    skipped = 0
    processed = 0
    cursor = 0

    while True:
        print(f'\nFetching list page from={cursor}...')
        page = fetch_offers_page(from_cursor=cursor)
        offers = page['data']
        total = page['meta']['totalItems']
        next_cursor = page['meta']['next']['cursor']

        print(f'Got {len(offers)} offers (total: {total})')

        for offer in offers:
            if limit is not None and processed >= limit:
                break


            slug = offer['slug']
            print(f'  Scraping detail: {slug}')
            try:
                detail = fetch_offer_detail(slug)
            except Exception as e:
                print(f'  ERROR fetching detail: {e}')
                skipped += 1
                continue

            job = map_job(offer, detail)

            if upsert_job(conn, job):
                inserted += 1
                print(f'  -> inserted')
            else:
                skipped += 1
                print(f'  -> already in DB, skipped')

            processed += 1
            time.sleep(0.3)

        if limit is not None and processed >= limit:
            break
        if not offers or next_cursor is None:
            break
        cursor = next_cursor

    conn.close()
    print(f'\nDone! Inserted: {inserted} new | Skipped: {skipped} duplicates')


if __name__ == '__main__':
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    main(limit=limit)
