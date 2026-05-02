"""
Visual audit: scroll through JJI website and collect all job slugs,
then compare with API results to find any gaps.

Handles JJI's virtual scroll (only ~20 items in DOM at a time)
by accumulating slugs across scroll positions.
"""
import time
import json
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

API_URL = 'https://justjoin.it/api/candidate-api/offers'
HEADERS = {
    'x-api-version': '1',
    'accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
}


def collect_from_website():
    """Scroll through JJI website and collect all job slugs from virtual scroll."""
    print('=== PHASE 1: Visual scrape (Selenium, virtual-scroll aware) ===')
    driver = webdriver.Chrome()
    driver.get('https://justjoin.it/job-offers/all-locations/java')

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/job-offer/"]'))
    )
    time.sleep(3)

    all_slugs = set()
    scroll_pos = 0
    scroll_step = 800
    stale_rounds = 0
    prev_total = 0

    while True:
        # Collect currently visible slugs
        visible = driver.execute_script("""
            const links = document.querySelectorAll('a[href*="/job-offer/"]');
            const slugs = [];
            links.forEach(a => {
                const href = a.getAttribute('href');
                if (href) {
                    const slug = href.split('/').pop();
                    if (slug) slugs.push(slug);
                }
            });
            return slugs;
        """)
        for s in visible:
            all_slugs.add(s)

        if len(all_slugs) % 100 < 20 or len(all_slugs) != prev_total:
            print(f'  scroll={scroll_pos}, visible={len(visible)}, accumulated={len(all_slugs)}')

        if len(all_slugs) == prev_total:
            stale_rounds += 1
            if stale_rounds >= 15:
                break
        else:
            stale_rounds = 0
            prev_total = len(all_slugs)

        scroll_pos += scroll_step
        driver.execute_script(f'window.scrollTo(0, {scroll_pos})')
        time.sleep(0.4)

    driver.quit()
    print(f'\nWebsite total: {len(all_slugs)} unique slugs')
    return all_slugs


def collect_from_api():
    """Paginate through JJI API and collect all job slugs."""
    print('\n=== PHASE 2: API scrape ===')
    all_slugs = set()
    cursor = 0

    while True:
        params = [
            ('categories', 'java'),
            ('from', cursor),
            ('itemsCount', 100),
            ('orderBy', 'descending'),
            ('sortBy', 'publishedAt'),
            ('keywordType', 'any'),
        ]
        r = requests.get(API_URL, headers=HEADERS, params=params)
        r.raise_for_status()
        data = r.json()
        offers = data['data']
        total = data['meta']['totalItems']

        for o in offers:
            all_slugs.add(o['slug'])

        print(f'  Page from={cursor}: got {len(offers)}, running total={len(all_slugs)} (API says {total})')

        next_info = data['meta']['next']
        if not offers or next_info is None or next_info.get('cursor') is None:
            break
        cursor = next_info['cursor']

    print(f'\nAPI total: {len(all_slugs)} unique slugs')
    return all_slugs


def main():
    website_slugs = collect_from_website()
    api_slugs = collect_from_api()

    only_website = website_slugs - api_slugs
    only_api = api_slugs - website_slugs
    common = website_slugs & api_slugs

    print('\n' + '=' * 60)
    print(f'  Website (visual scroll): {len(website_slugs)}')
    print(f'  API (paginated):         {len(api_slugs)}')
    print(f'  Common:                  {len(common)}')
    print(f'  Only on website (API misses): {len(only_website)}')
    print(f'  Only in API (not on website): {len(only_api)}')
    print('=' * 60)

    if only_website:
        print(f'\n--- Jobs ONLY on website ({len(only_website)}) — these are what API misses ---')
        for s in sorted(only_website):
            print(f'  https://justjoin.it/job-offer/{s}')

    if only_api:
        print(f'\n--- Jobs ONLY in API ({len(only_api)}) — not shown on website ---')
        for s in sorted(only_api)[:20]:
            print(f'  https://justjoin.it/job-offer/{s}')
        if len(only_api) > 20:
            print(f'  ... and {len(only_api) - 20} more')

    results = {
        'website_count': len(website_slugs),
        'api_count': len(api_slugs),
        'common': len(common),
        'only_website_count': len(only_website),
        'only_api_count': len(only_api),
        'only_website': sorted(only_website),
        'only_api': sorted(only_api),
    }
    with open('scrapers/jji_audit_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nFull results saved to scrapers/jji_audit_results.json')


if __name__ == '__main__':
    main()
