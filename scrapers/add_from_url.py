"""
Add a job from URL. Detects platform and dispatches to the right scraper.
Supports: justjoinit, nofluffjobs. Other platforms use LLM extraction.

Usage:
  python scrapers/add_from_url.py <url>
"""
import sys
import os
import re
import json
import requests
import pymysql
import pymysql.cursors
from datetime import date
from urllib.parse import urlparse
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_CONFIG as _DB_BASE

DB_CONFIG = {**_DB_BASE, 'cursorclass': pymysql.cursors.DictCursor}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/122.0.0.0 Safari/537.36'
    ),
}


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def detect_platform(url: str) -> str:
    domain = urlparse(url).netloc.lower()
    if 'justjoin.it' in domain:
        return 'justjoinit'
    if 'nofluffjobs.com' in domain:
        return 'nofluffjobs'
    return 'generic'


def scrape_justjoinit(url: str) -> dict:
    slug = url.rstrip('/').split('/')[-1]
    api_url = f'https://justjoin.it/api/candidate-api/offers/{slug}'
    headers = {**HEADERS, 'x-api-version': '1', 'accept': 'application/json'}
    resp = requests.get(api_url, headers=headers)
    resp.raise_for_status()
    detail = resp.json()

    from justjoinit_scraper import map_job, format_salary
    offer = {
        'slug': slug,
        'title': detail.get('title'),
        'companyName': detail.get('companyName'),
        'experienceLevel': detail.get('experienceLevel', ''),
        'employmentTypes': detail.get('employmentTypes', []),
        'expiredAt': detail.get('expiredAt'),
        'publishedAt': detail.get('publishedAt'),
        'requiredSkills': detail.get('requiredSkills', []),
        'niceToHaveSkills': detail.get('niceToHaveSkills', []),
        'workplaceType': detail.get('workplaceType'),
        'workingTime': detail.get('workingTime'),
        'city': detail.get('city'),
    }
    return map_job(offer, detail)


def scrape_nofluffjobs(url: str) -> dict:
    from nofluffscraper import scrape_job_details
    return scrape_job_details(url)


def scrape_generic(url: str) -> dict:
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, 'html.parser')

    for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
        tag.decompose()
    text = soup.get_text(separator='\n', strip=True)
    text = re.sub(r'\n{3,}', '\n\n', text)[:6000]

    from openai import OpenAI
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
    client = OpenAI(
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        base_url='https://api.deepseek.com',
    )

    prompt = f"""Extract job posting details from this page text. Return ONLY valid JSON with these fields:
- "position": job title (string)
- "company": company name (string)
- "seniority": one of "Junior", "Mid", "Senior", "Lead" or comma-separated (string)
- "salary": salary info if present, else null (string or null)
- "requirements_must": list of required skills/technologies (array of strings)
- "requirements_nice": list of nice-to-have skills (array of strings)
- "job_description": full job description text, preserved structure (string)
- "expires_at": expiration date if found, format YYYY-MM-DD (string or null)

Page text:
{text}"""

    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=[
            {'role': 'system', 'content': 'You extract structured job data from web pages. Return ONLY valid JSON.'},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0.1,
        max_tokens=2000,
        response_format={'type': 'json_object'},
    )
    data = json.loads(response.choices[0].message.content.strip())

    domain = urlparse(url).netloc.replace('www.', '')
    slug = url.rstrip('/').split('/')[-1]
    job_id = re.sub(r'[^\w\-]', '_', slug)[:200]

    return {
        'id': job_id,
        'position': data.get('position', 'Unknown'),
        'company': data.get('company', 'Unknown'),
        'seniority': data.get('seniority'),
        'salary': data.get('salary'),
        'expires_at': data.get('expires_at'),
        'posted_at': date.today(),
        'requirements_must': data.get('requirements_must', []),
        'requirements_nice': data.get('requirements_nice', []),
        'extra_details': {'source_domain': domain},
        'job_description': data.get('job_description', ''),
        'url': url,
    }


def upsert_job(conn, job: dict, source: str) -> bool:
    expires_at = job.get('expires_at')
    if isinstance(expires_at, str):
        from datetime import datetime
        try:
            expires_at = datetime.strptime(expires_at, '%Y-%m-%d').date()
        except ValueError:
            expires_at = None

    with conn.cursor() as cur:
        rows = cur.execute("""
            INSERT IGNORE INTO jobs
                (id, source, position, company, seniority, salary,
                 expires_at, scraped_at, posted_at, requirements_must, requirements_nice,
                 extra_details, job_description, url)
            VALUES
                (%s, %s, %s, %s, %s, %s,
                 %s, %s, %s, %s, %s,
                 %s, %s, %s)
        """, (
            job['id'],
            source,
            job.get('position'),
            job.get('company'),
            job.get('seniority'),
            job.get('salary'),
            expires_at,
            date.today(),
            job.get('posted_at'),
            json.dumps(job.get('requirements_must', []), ensure_ascii=False),
            json.dumps(job.get('requirements_nice', []), ensure_ascii=False),
            json.dumps(job.get('extra_details', {}), ensure_ascii=False),
            job.get('job_description'),
            job['url'],
        ))
    conn.commit()
    return rows == 1


def main():
    if len(sys.argv) < 2:
        print('Usage: python scrapers/add_from_url.py <url>')
        sys.exit(1)

    url = sys.argv[1].strip()
    platform = detect_platform(url)
    print(f'🔗  URL: {url}')
    print(f'📦  Platform: {platform}')

    try:
        if platform == 'justjoinit':
            job = scrape_justjoinit(url)
            source = 'justjoinit'
        elif platform == 'nofluffjobs':
            job = scrape_nofluffjobs(url)
            source = 'nofluffjobs'
        else:
            job = scrape_generic(url)
            source = urlparse(url).netloc.replace('www.', '').split('.')[0]
    except Exception as e:
        print(f'❌  Scraping failed: {e}')
        sys.exit(1)

    print(f'📋  Position: {job.get("position")}')
    print(f'🏢  Company: {job.get("company")}')
    print(f'📊  Seniority: {job.get("seniority")}')
    print(f'🔧  Must-have: {job.get("requirements_must", [])}')

    conn = get_connection()
    inserted = upsert_job(conn, job, source)
    conn.close()

    if inserted:
        print(f'\n✅  Job added: {job["id"]} ({source})')
    else:
        print(f'\n⚠️  Job already exists: {job["id"]} ({source})')


if __name__ == '__main__':
    main()
