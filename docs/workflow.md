# 1. Scrape new jobs (daily, ~2 min)
python scrapers/justjoinit_scraper.py
python scrapers/nofluffscraper.py
# or run all at once:
python scrapers/scrape_all.py

# 2. Score new jobs with AI (auto, ~3 min for 100 jobs)
#    Also classifies each job as 'crp' (corporate) or 'igm' (iGaming/startups)
python pipeline/score_jobs.py

# 3. Generate tailored CVs text for all scored >= 60 (auto, ~5 min)
#    Automatically uses the correct master CV variant (crp/igm) per job
python pipeline/tailor_cv.py

# 4. Batch render ALL tailored CVs to PDF (auto, ~1 min per 10 PDFs)
#    Uses the correct HTML template (crp/igm) per job
python pipeline/generate_cv.py --batch --min-score 70
python pipeline/generate_cv.py --list --open --min-score 70

# Generate default (non-tailored) CV for a specific variant
python pipeline/generate_cv.py --default --variant crp
python pipeline/generate_cv.py --default --variant igm
