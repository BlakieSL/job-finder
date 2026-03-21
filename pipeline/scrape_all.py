"""
scrape_all.py
-------------
Runs all scrapers sequentially: JustJoinIT first (fast, API-based),
then NoFluffJobs (slower, Selenium-based).

Usage:
    python scrape_all.py            # full run
    python scrape_all.py --limit 10 # limit JJI to N jobs (for testing)
"""

import argparse
import sys
import time

import justjoinit_scraper
import nofluffscraper


def main():
    parser = argparse.ArgumentParser(description='Run all job scrapers')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit JustJoinIT to N jobs (for testing)')
    args = parser.parse_args()

    total_start = time.time()

    # ── 1. JustJoinIT ─────────────────────────────────────────────────────────
    print('=' * 60)
    print('  SCRAPER 1/2 — JustJoinIT')
    print('=' * 60)
    try:
        justjoinit_scraper.main(limit=args.limit)
    except Exception as e:
        print(f'ERROR in JustJoinIT scraper: {e}')

    print()

    # ── 2. NoFluffJobs ────────────────────────────────────────────────────────
    print('=' * 60)
    print('  SCRAPER 2/2 — NoFluffJobs')
    print('=' * 60)
    try:
        nofluffscraper.main()
    except Exception as e:
        print(f'ERROR in NoFluffJobs scraper: {e}')

    elapsed = time.time() - total_start
    print()
    print('=' * 60)
    print(f'  All scrapers done in {elapsed:.0f}s')
    print('  Next step: python score_jobs.py')
    print('=' * 60)


if __name__ == '__main__':
    main()
