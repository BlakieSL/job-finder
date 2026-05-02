"""
Visual audit: scroll through NoFluffJobs website and collect all job slugs,
then compare with what our scraper URLs return.
"""
import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def collect_from_url(driver, url, all_slugs):
    """Load a NoFluff search URL, click all 'load more', collect slugs."""
    print(f'\n  Loading: {url}')
    driver.get(url)

    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'nfj-postings-list[listname="search"] a[href*="/job/"]'))
        )
    except Exception:
        print('    No results found on this page')
        return

    # Click load more until exhausted
    while True:
        try:
            button = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'button[nfjloadmore]'))
            )
            driver.execute_script("arguments[0].scrollIntoView(); arguments[0].click();", button)
            time.sleep(2)
        except:
            break

    slugs = driver.execute_script("""
        const seen = new Set();
        document.querySelectorAll('nfj-postings-list[listname="search"] a[href*="/job/"]').forEach(a => {
            const href = a.getAttribute('href');
            if (href) {
                const slug = href.split('/').pop();
                if (slug) seen.add(slug);
            }
        });
        return [...seen];
    """)

    before = len(all_slugs)
    for s in slugs:
        all_slugs.add(s)
    new = len(all_slugs) - before
    print(f'    Found {len(slugs)} slugs on page, {new} new (total: {len(all_slugs)})')


def main():
    driver = webdriver.Chrome()

    # === 1. Our scraper URLs (what we currently scrape) ===
    print('=== PHASE 1: Our scraper URLs ===')
    our_urls = [
        'https://nofluffjobs.com/pl/Java?lang=en',
        'https://nofluffjobs.com/pl/praca-zdalna/Java?lang=en',
        'https://nofluffjobs.com/pl/hybrid/Java?lang=en',
    ]
    our_slugs = set()
    for url in our_urls:
        collect_from_url(driver, url, our_slugs)
    print(f'\nOur scraper total: {len(our_slugs)}')

    # === 2. The "4k" page — no filters at all, just Java tech ===
    print('\n=== PHASE 2: Website "all" page (what shows 4k) ===')
    # The screenshot showed this URL with just Java selected in tech filter
    all_urls = [
        'https://nofluffjobs.com/pl/Java',  # no lang=en, no work mode filter
    ]
    website_slugs = set()
    for url in all_urls:
        collect_from_url(driver, url, website_slugs)
    print(f'\nWebsite "all" total: {len(website_slugs)}')

    # === 3. Breakdown by work mode without lang=en ===
    print('\n=== PHASE 3: Breakdown by work mode (no lang=en) ===')
    mode_urls = {
        'on-site (no lang)': 'https://nofluffjobs.com/pl/Java',
        'remote (no lang)': 'https://nofluffjobs.com/pl/praca-zdalna/Java',
        'hybrid (no lang)': 'https://nofluffjobs.com/pl/hybrid/Java',
        'on-site (lang=en)': 'https://nofluffjobs.com/pl/Java?lang=en',
        'remote (lang=en)': 'https://nofluffjobs.com/pl/praca-zdalna/Java?lang=en',
        'hybrid (lang=en)': 'https://nofluffjobs.com/pl/hybrid/Java?lang=en',
    }
    for label, url in mode_urls.items():
        mode_slugs = set()
        collect_from_url(driver, url, mode_slugs)
        print(f'    {label}: {len(mode_slugs)} slugs')

    driver.quit()

    # === Compare ===
    only_website = website_slugs - our_slugs
    only_ours = our_slugs - website_slugs
    common = website_slugs & our_slugs

    print('\n' + '=' * 60)
    print(f'  Our scraper URLs:     {len(our_slugs)}')
    print(f'  Website "all" page:   {len(website_slugs)}')
    print(f'  Common:               {len(common)}')
    print(f'  Only on website (we miss): {len(only_website)}')
    print(f'  Only in ours (not on website): {len(only_ours)}')
    print('=' * 60)

    if only_website:
        print(f'\n--- We MISS these ({len(only_website)}) ---')
        for s in sorted(only_website)[:30]:
            print(f'  https://nofluffjobs.com/pl/job/{s}')
        if len(only_website) > 30:
            print(f'  ... and {len(only_website) - 30} more')

    results = {
        'our_count': len(our_slugs),
        'website_count': len(website_slugs),
        'common': len(common),
        'only_website_count': len(only_website),
        'only_ours_count': len(only_ours),
        'only_website': sorted(only_website),
        'only_ours': sorted(only_ours),
    }
    with open('scrapers/nfj_audit_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nFull results saved to scrapers/nfj_audit_results.json')


if __name__ == '__main__':
    main()
