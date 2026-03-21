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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG as _DB_BASE

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

SOURCE = 'nofluffjobs'

# Known sidebar/noise sections to exclude from extra_details
EXCLUDED_SECTIONS = {'Perks in office', 'Benefits', 'Udogodnienia w biurze', 'Benefity'}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_connection():
    return pymysql.connect(**DB_CONFIG)


def ensure_schema(conn):
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
        # Add any missing columns for existing tables (safe to run repeatedly)
        migrations = [
            "ALTER TABLE jobs ADD COLUMN job_description TEXT AFTER extra_details",
            "ALTER TABLE jobs ADD COLUMN fit_score TINYINT UNSIGNED DEFAULT NULL AFTER status",
            "ALTER TABLE jobs ADD COLUMN fit_notes VARCHAR(500) DEFAULT NULL AFTER fit_score",
        ]
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception:
                pass  # Column already exists — ignore
    conn.commit()


def normalize_seniority_case(conn):
    """Capitalize the first letter of every seniority word in the DB.

    Examples:
        'senior'        -> 'Senior'
        'mid junior'    -> 'Mid, Junior'   (already stored normalized, just re-caps)
        'SENIOR, MID'   -> 'Senior, Mid'
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, source, seniority FROM jobs WHERE seniority IS NOT NULL")
        rows = cur.fetchall()
        updated = 0
        for row in rows:
            raw = row['seniority']
            # Split on comma or whitespace, capitalize each token, rejoin with ', '
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


def upsert_job(conn, job: dict) -> bool:
    """Insert job, skip if URL already exists. Returns True if inserted."""
    # Parse expires_at string DD.MM.YYYY -> date object (or None)
    expires_at = None
    raw_expires = job.get('expires_at', '')
    if raw_expires:
        try:
            expires_at = datetime.strptime(raw_expires, '%d.%m.%Y').date()
        except ValueError:
            pass

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
            expires_at,
            date.today(),
            json.dumps(job.get('requirements_must', []), ensure_ascii=False),
            json.dumps(job.get('requirements_nice', []), ensure_ascii=False),
            json.dumps(job.get('extra_details', {}), ensure_ascii=False),
            job.get('job_description'),
            job['url'],
        ))
    conn.commit()
    return rows == 1


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def parse_salary_block(block):
    range_el = block.find('h4', class_='tw-mb-0')
    type_el = block.find('div', class_='paragraph')

    if not range_el or not type_el:
        return None

    raw_range = range_el.get_text(' ', strip=True)
    currency_match = re.search(r'[A-Z]{3}$', raw_range)
    currency = currency_match.group(0) if currency_match else ''
    nums = re.findall(r'[\d\s]+', raw_range)
    nums = [n.replace(' ', '').replace('\xa0', '') for n in nums if n.strip()]
    rate_min = nums[0] if len(nums) > 0 else ''
    rate_max = nums[1] if len(nums) > 1 else ''

    span = type_el.find('span')
    type_text = span.get_text(' ', strip=True).lower() if span else ''

    if 'b2b' in type_text:
        contract = 'B2B'
    elif 'uop' in type_text or 'employment' in type_text or 'brutto' in type_text:
        contract = 'UoP'
    else:
        contract = type_text

    if 'godzin' in type_text or 'hour' in type_text:
        period = 'hourly'
    else:
        period = 'monthly'

    return {
        'contract': contract,
        'period': period,
        'rate_min': rate_min,
        'rate_max': rate_max,
        'currency': currency,
    }


def scrape_job_details(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # ID = slug from URL, e.g. "senior-java-developer-link-group-warszawa-9"
    job_id = url.rstrip('/').split('/')[-1]

    job_title_el = soup.find('h1', class_='font-weight-bold')
    job_title = job_title_el.text.strip() if job_title_el else 'Not found'

    company_el = soup.find('a', id='postingCompanyUrl')
    company = company_el.text.strip() if company_el else 'Not found'

    seniority_el = soup.find('li', id='posting-seniority')
    try:
        raw_seniority = seniority_el.text.strip() if seniority_el else ''
    except AttributeError:
        raw_seniority = ''
    # Normalize: "Mid Junior" → "Mid, Junior"; ensure Title Case
    seniority = ', '.join(w.capitalize() for w in raw_seniority.split()) if raw_seniority else None

    # Salary — only the first two .salary blocks (the sidebar repeats them)
    salary_blocks = soup.find_all('div', class_='salary')[:2]
    salary_parts = []
    for block in salary_blocks:
        parsed = parse_salary_block(block)
        if not parsed or not parsed['rate_min']:
            continue
        rate = f"{parsed['rate_min']}–{parsed['rate_max']} {parsed['currency']}"
        salary_parts.append(f"{parsed['contract']} {rate} {parsed['period']}")
    salary = ' | '.join(salary_parts) if salary_parts else 'Not disclosed'

    # Requirements
    requirements_must = []
    requirements_nice = []
    for req_type in ['musts', 'nices']:
        section = soup.find('section', attrs={'branch': req_type})
        if section:
            items = [span.text.strip() for li in section.find_all('li') for span in li.find_all('span')]
            if req_type == 'musts':
                requirements_must = items
            else:
                requirements_nice = items

    def clean_section(el):
        """Extract text from a section, stripping Polish UI labels and translation prompts."""
        text = el.get_text(' ', strip=True)
        text = re.sub(r'Oryginalny tekst\.?\s*Pokaż tłumaczenie', '', text)
        text = re.sub(r'^(Opis oferty|Zakres obowiązków|Opis wymagań)\s*', '', text).strip()
        return text or None

    # Role overview
    role_overview = None
    el = soup.find('section', id='posting-description')
    if el:
        role_overview = clean_section(el)

    # Daily tasks
    daily_tasks = None
    el = soup.find('section', id='posting-tasks')
    if el:
        daily_tasks = clean_section(el)

    # Requirements prose — section with data-cy-section="JobOffer_Requirements"
    requirements_description = None
    el = soup.find('section', attrs={'data-cy-section': 'JobOffer_Requirements'})
    if el:
        requirements_description = clean_section(el)

    # Build full job description with labeled sections for AI context
    description_parts = []
    if role_overview:
        description_parts.append(f"## Role Overview\n{role_overview}")
    if daily_tasks:
        description_parts.append(f"## Daily Tasks\n{daily_tasks}")
    if requirements_description:
        description_parts.append(f"## Requirements Description\n{requirements_description}")
    job_description = '\n\n'.join(description_parts) if description_parts else None

    # Expires at — page is in Polish: "Oferta ważna do: 02.04.2026 (zostało X dni)"
    expires_at = ''
    valid_match = re.search(r'(\d{2}\.\d{2}\.20\d{2})', soup.get_text())
    if valid_match:
        expires_at = valid_match.group(1)

    # Job details (location, remote, etc.) — stored as JSON blob
    posting_specs_el = soup.find('section', id='posting-specs')
    details = posting_specs_el.find_all('li', class_='detail') if posting_specs_el else []
    extra_details = {}
    for detail in details:
        key_el = detail.find('h3', class_='tw-text-sm')
        val_el = detail.find('span')
        if key_el and val_el:
            key = key_el.text.strip(':').strip()
            if key not in EXCLUDED_SECTIONS:
                extra_details[key] = val_el.text.strip()

    return {
        'id': job_id,
        'position': job_title,
        'company': company,
        'seniority': seniority,
        'salary': salary,
        'expires_at': expires_at,
        'requirements_must': requirements_must,
        'requirements_nice': requirements_nice,
        'extra_details': extra_details,
        'job_description': job_description,
        'url': url,
    }


def scrape_listings(driver, url, base_url, scraped_links):
    print(f'\nLoading: {url}')
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'nfj-postings-list[listname="search"] a[href*="/job/"]'))
    )

    while True:
        try:
            button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[nfjloadmore]'))
            )
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", button)
            time.sleep(3)
        except:
            break

    links = driver.execute_script("""
        const seen = new Set();
        const result = [];
        document.querySelectorAll('nfj-postings-list[listname="search"] a[href*="/job/"]').forEach(a => {
            const href = a.getAttribute('href');
            if (href && !seen.has(href)) { seen.add(href); result.push(href); }
        });
        return result;
    """)

    new_links = [l for l in links if l not in scraped_links]
    print(f'Found {len(new_links)} new job links (skipping {len(links) - len(new_links)} duplicates)')
    return new_links


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    base_url = 'https://nofluffjobs.com'
    search_urls = [
        # Warsaw office/on-site (added — was missing before)
        'https://nofluffjobs.com/pl/warszawa/Java?lang=en',
        # Remote — all Poland (catches remote jobs not city-tagged as Warsaw)
        'https://nofluffjobs.com/pl/praca-zdalna/Java?lang=en',
        # Remote — city=Warsaw explicitly
        'https://nofluffjobs.com/pl/praca-zdalna/Java?criteria=city%3Dwarszawa&lang=en',
        # Hybrid Warsaw
        'https://nofluffjobs.com/pl/hybrid/Java?criteria=city%3Dwarszawa&lang=en',
    ]
    # Seniority filter intentionally removed — NoFluff has jobs with no seniority tag
    # that would be silently skipped. AI scorer handles seniority relevance.
    # Duplicates across URLs are handled by INSERT IGNORE on unique url key.

    print('Connecting to MySQL...')
    conn = get_connection()
    ensure_schema(conn)
    print('Connected. Schema ready.')

    driver = webdriver.Chrome()

    scraped_links = set()
    inserted = 0
    skipped = 0

    for url in search_urls:
        new_links = scrape_listings(driver, url, base_url, scraped_links)
        for link in new_links:
            scraped_links.add(link)
            job_url = f'{base_url}{link}'
            print(f'Scraping: {job_url}')
            job = scrape_job_details(job_url)
            if upsert_job(conn, job):
                inserted += 1
            else:
                skipped += 1
                print(f'  -> already in DB, skipped')

    driver.quit()
    conn.close()

    print(f'\nDone! Inserted: {inserted} new | Skipped: {skipped} duplicates')


if __name__ == '__main__':
    main()
