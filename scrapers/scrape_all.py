"""
scrape_all.py
-------------
Runs all scrapers in parallel (JustJoinIT + NoFluffJobs + Pracuj.pl).

Usage:
    python scrape_all.py            # full run
    python scrape_all.py --limit 10 # limit JJI to N jobs (for testing)
"""

import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import justjoinit_scraper
import nofluffscraper
import pracuj_scraper


def _run_justjoinit(limit):
    print('=' * 60)
    print('  SCRAPER — JustJoinIT (parallel)')
    print('=' * 60)
    justjoinit_scraper.main(limit=limit)


def _run_nofluffjobs():
    print('=' * 60)
    print('  SCRAPER — NoFluffJobs (parallel)')
    print('=' * 60)
    nofluffscraper.main()


def _run_pracuj():
    print('=' * 60)
    print('  SCRAPER — Pracuj.pl (parallel)')
    print('=' * 60)
    pracuj_scraper.main()


def main():
    parser = argparse.ArgumentParser(description='Run all job scrapers')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit JustJoinIT to N jobs (for testing)')
    args = parser.parse_args()

    total_start = time.time()

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run_justjoinit, args.limit): 'JustJoinIT',
            pool.submit(_run_nofluffjobs): 'NoFluffJobs',
            pool.submit(_run_pracuj): 'Pracuj.pl',
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f'ERROR in {name} scraper: {e}')

    elapsed = time.time() - total_start
    print()
    print('=' * 60)
    print(f'  All scrapers done in {elapsed:.0f}s')
    print('  Next step: python score_jobs.py')
    print('=' * 60)


if __name__ == '__main__':
    main()
