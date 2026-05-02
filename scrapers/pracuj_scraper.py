"""
Pracuj.pl scraper — uses Selenium to load SSR pages and extract job data
from __NEXT_DATA__ JSON embedded by Next.js.

Pracuj groups multi-location jobs into a single listing. Each group has
one jobTitle/company but multiple offers (locations). We store one row
per group, using the first location as the city.
"""
import re
import json
import os
import sys
import time
import random
import pymysql
import pymysql.cursors
from datetime import date, datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG as _DB_BASE

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

SOURCE = 'pracuj'
BASE_URL = 'https://it.pracuj.pl/praca/java;kw?pn={page}'
PAGE_DELAY_MIN = 10
PAGE_DELAY_MAX = 18
MAX_PAGES = 30

POLISH_MARKERS = re.compile(
    r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]'
    r'|(?<!\w)(?:wymagania|doświadczenie|praca|zespół|aplikuj|obowiązki|umiejętności|znajomość'
    r'|wynagrodzenie|oferujemy|oczekujemy|zapewniamy|poszukujemy|stanowisko)(?!\w)',
    re.IGNORECASE,
)

SENIORITY_MAP = {
    'praktykant / stażysta': 'Trainee',
    'praktykantka / stażystka': 'Trainee',
    'asystent': 'Trainee',
    'asystentka': 'Trainee',
    'młodszy specjalista (junior)': 'Junior',
    'młodsza specjalistka (junior)': 'Junior',
    'specjalista (mid / regular)': 'Mid',
    'specjalistka (mid / regular)': 'Mid',
    'starszy specjalista (senior)': 'Senior',
    'starsza specjalistka (senior)': 'Senior',
    'ekspert': 'Senior',
    'ekspertka': 'Senior',
    'kierownik / kierowniczka - koordynator / koordynatorka': 'Lead',
    'kierownik / koordynator': 'Lead',
    'menedżer / menedżerka': 'Manager',
    'menedżer': 'Manager',
    'dyrektor / dyrektorka': 'Manager',
    'dyrektor': 'Manager',
}


def detect_language(text: str) -> str:
    if not text:
        return 'en'
    hits = len(POLISH_MARKERS.findall(text[:3000]))
    return 'pl' if hits >= 3 else 'en'


def normalize_seniority(levels: list) -> str:
    if not levels:
        return None
    mapped = set()
    for lvl in levels:
        key = lvl.strip().lower()
        mapped.add(SENIORITY_MAP.get(key, lvl.strip()))
    return ', '.join(sorted(mapped))


def extract_city(offers: list, work_modes: list, is_remote: bool) -> str:
    if is_remote and (not offers or all(o.get('isWholePoland') for o in offers)):
        return 'Fully Remote'
    wm = [m.lower() for m in (work_modes or [])]
    if any('zdaln' in m for m in wm) and not offers:
        return 'Fully Remote'
    if offers:
        city = offers[0].get('displayWorkplace', '')
        if city:
            return city.split(',')[0].strip()
    return 'Fully Remote'


def format_salary(salary_text: str) -> str:
    if not salary_text or not salary_text.strip():
        return 'Not disclosed'
    return salary_text.strip()


def map_job(group: dict) -> dict:
    offers = group.get('offers', [])
    work_modes = group.get('workModes', [])
    is_remote = group.get('isRemoteWorkAllowed', False)

    job_id = group['groupId']

    posted_at = None
    raw_pub = group.get('lastPublicated', '')
    if raw_pub:
        try:
            posted_at = datetime.fromisoformat(raw_pub.replace('Z', '+00:00')).date()
        except ValueError:
            pass

    expires_at = None
    raw_exp = group.get('expirationDate', '')
    if raw_exp:
        try:
            expires_at = datetime.fromisoformat(raw_exp.replace('Z', '+00:00')).date()
        except ValueError:
            pass

    url = offers[0]['offerAbsoluteUri'] if offers else f'https://it.pracuj.pl/praca/java;kw'

    job_description = group.get('jobDescription', '') or ''
    about = group.get('aboutProjectShortDescription', '') or ''
    if about:
        job_description = f"## About Project\n{about}\n\n{job_description}"

    language = detect_language(job_description)

    extra_details = {
        'workModes': work_modes,
        'workSchedules': group.get('workSchedules', []),
        'typesOfContract': group.get('typesOfContract', []),
        'locationsCount': len(offers),
    }

    return {
        'id': job_id,
        'position': group['jobTitle'],
        'company': group['companyName'],
        'seniority': normalize_seniority(group.get('positionLevels', [])),
        'salary': format_salary(group.get('salaryDisplayText', '')),
        'expires_at': expires_at,
        'posted_at': posted_at,
        'requirements_must': group.get('technologies', []),
        'requirements_nice': [],
        'extra_details': extra_details,
        'job_description': job_description,
        'language': language,
        'city': extract_city(offers, work_modes, is_remote),
        'url': url,
    }


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
        migrations = [
            "ALTER TABLE jobs ADD COLUMN fit_score TINYINT UNSIGNED DEFAULT NULL AFTER status",
            "ALTER TABLE jobs ADD COLUMN fit_notes VARCHAR(500) DEFAULT NULL AFTER fit_score",
            "ALTER TABLE jobs ADD COLUMN posted_at DATE DEFAULT NULL AFTER scraped_at",
            "ALTER TABLE jobs ADD COLUMN language VARCHAR(10) NOT NULL DEFAULT 'en' AFTER job_description",
            "ALTER TABLE jobs ADD COLUMN city VARCHAR(255) DEFAULT NULL AFTER language",
        ]
        for sql in migrations:
            try:
                cur.execute(sql)
            except Exception:
                pass
    conn.commit()


def upsert_job(conn, job: dict) -> bool:
    with conn.cursor() as cur:
        rows = cur.execute("""
            INSERT IGNORE INTO jobs
                (id, source, position, company, seniority, salary,
                 expires_at, scraped_at, posted_at, requirements_must, requirements_nice,
                 extra_details, job_description, language, city, url)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s)
        """, (
            job['id'],
            SOURCE,
            job.get('position'),
            job.get('company'),
            job.get('seniority'),
            job.get('salary'),
            job.get('expires_at'),
            date.today(),
            job.get('posted_at'),
            json.dumps(job.get('requirements_must', []), ensure_ascii=False),
            json.dumps(job.get('requirements_nice', []), ensure_ascii=False),
            json.dumps(job.get('extra_details', {}), ensure_ascii=False),
            job.get('job_description'),
            job.get('language', 'en'),
            job.get('city'),
            job['url'],
        ))
    conn.commit()
    return rows == 1


def handle_cloudflare(driver, timeout=45):
    """Detect and handle Cloudflare Turnstile challenge."""
    for i in range(timeout):
        try:
            driver.find_element(By.ID, '__NEXT_DATA__')
            return True
        except:
            pass
        # Check for Turnstile iframe and click it
        try:
            iframes = driver.find_elements(By.CSS_SELECTOR, 'iframe[src*="challenges.cloudflare"]')
            if iframes:
                if i == 3:
                    print('    Cloudflare challenge detected, solving...')
                for iframe in iframes:
                    try:
                        driver.switch_to.frame(iframe)
                        cb = driver.find_element(By.CSS_SELECTOR, 'input[type="checkbox"], .ctp-checkbox-label')
                        cb.click()
                        driver.switch_to.default_content()
                        time.sleep(5)
                        break
                    except:
                        driver.switch_to.default_content()
        except:
            pass
        time.sleep(1)
    return False


def extract_offers_from_page(driver) -> list:
    """Extract grouped offers from __NEXT_DATA__ on current page."""
    try:
        el = driver.find_element(By.ID, '__NEXT_DATA__')
        data = json.loads(el.get_attribute('textContent'))
        queries = data['props']['pageProps']['dehydratedState']['queries']
        for q in queries:
            d = q['state'].get('data', {})
            if 'groupedOffers' in d:
                return d['groupedOffers']
    except Exception as e:
        print(f'  ERROR extracting offers: {e}')
    return []


def main():
    print('Connecting to MySQL...')
    conn = get_connection()
    ensure_schema(conn)
    print('Connected. Schema ready.')

    opts = Options()
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    })

    inserted = 0
    skipped = 0
    page = 1

    while page <= MAX_PAGES:
        url = BASE_URL.format(page=page)
        print(f'\nPage {page}: {url}')
        driver.get(url)

        if not handle_cloudflare(driver):
            print(f'  Page {page} failed (Cloudflare), retrying after 20s...')
            time.sleep(20)
            driver.get(url)
            if not handle_cloudflare(driver):
                print(f'  Page {page} failed again, stopping.')
                break

        # Accept cookies on first page
        if page == 1:
            try:
                btn = driver.find_element(By.XPATH, '//button[contains(text(), "Akceptuj wszystkie")]')
                btn.click()
                time.sleep(1)
            except:
                pass

        groups = extract_offers_from_page(driver)
        print(f'  Got {len(groups)} job groups')

        if not groups:
            print('  No more offers, stopping.')
            break

        for group in groups:
            job = map_job(group)
            if upsert_job(conn, job):
                inserted += 1
            else:
                skipped += 1

        if len(groups) < 50:
            print(f'  Last page (got {len(groups)} < 50)')
            break

        page += 1
        delay = random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX)
        print(f'  Waiting {delay:.1f}s...')
        time.sleep(delay)

    driver.quit()
    conn.close()
    print(f'\nDone! Inserted: {inserted} new | Skipped: {skipped} duplicates')


if __name__ == '__main__':
    main()
