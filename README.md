# Job Application Pipeline

## About

An automated job application pipeline that scrapes job postings from Polish tech platforms, scores them against a candidate profile using AI, tailors CVs per job, and generates print-ready PDFs — all managed through a web dashboard. Built for a Java/Kotlin backend engineer targeting mid-level positions in Poland.

The system combines Python scrapers, a DeepSeek-powered AI scoring and tailoring engine, a FastAPI backend, and a React dashboard. Jobs flow through a five-stage pipeline: scrape → score → tailor → generate PDF → apply.

**Tech Stack:** Python | FastAPI | React 19 | TypeScript | MySQL 8.0 | DeepSeek API | Selenium | Tailwind CSS | Docker

**Dashboard:** `http://localhost:5173` (dev)

---

## Features

| Domain | Capabilities |
|---|---|
| Scraping | Multi-platform ingestion from JustJoinIT (REST API) and NoFluffJobs (Selenium), deduplication via unique URL constraint |
| AI Scoring | DeepSeek-powered fit scoring (0–100) with seniority gating, tech match analysis, and automatic CV variant classification |
| CV Tailoring | AI-generated title and summary, programmatic skill reordering, safe skill additions from approved list — zero fabrication of experience |
| PDF Generation | Headless Chrome rendering of HTML templates with injected tailored content, batch processing |
| Dual CV System | Corporate (`crp`) and iGaming/startup (`igm`) variants with separate master CVs and HTML templates |
| Dashboard | Full-stack web UI for filtering, reviewing, triggering pipeline actions, and downloading PDFs |
| Analytics | Stats bar with job counts by status, score-based filtering, search across positions and companies |

---

## Usage

### Installation

```bash
git clone <repository-url>
cd PythonProject
cp .env.example .env        # Fill in your DeepSeek API key
docker-compose up -d        # Start MySQL
pip install -r requirements.txt
```

### Pipeline Commands

| Command | Description |
|---|---|
| `python pipeline/scrape_all.py` | Scrape jobs from all platforms |
| `python pipeline/score_jobs.py` | Score new jobs with AI |
| `python pipeline/tailor_cv.py --min-score 60` | Tailor CVs for scored jobs above threshold |
| `python pipeline/generate_cv.py --batch` | Generate PDFs for all tailored jobs |
| `python pipeline/generate_cv.py --default --variant crp` | Generate default (non-tailored) CV |

### Dashboard

```bash
# Terminal 1: Backend API (port 8001)
cd dashboard/backend
python main.py

# Terminal 2: Frontend dev server (port 5173)
cd dashboard/frontend
npm install
npm run dev
```

---

## Development

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker
- Chrome/Chromium (for PDF generation)

### Environment Setup

Create `.env` in the project root:

```properties
DEEPSEEK_API_KEY=sk-...
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=job_tracker
```

Start MySQL:

```bash
docker-compose up -d
```

### File Structure

```
├── pipeline/                    # Core AI pipeline scripts
│   ├── scrape_all.py           # Orchestrator for all scrapers
│   ├── score_jobs.py           # AI job fit scoring
│   ├── tailor_cv.py            # AI-powered CV tailoring
│   └── generate_cv.py          # PDF rendering via headless Chrome
│
├── scrapers/                    # Job platform scrapers
│   ├── justjoinit_scraper.py   # REST API-based (fast)
│   └── nofluffscraper.py       # Selenium-based (thorough)
│
├── cv/                          # CV assets
│   ├── master/                 # Master CV markdown files (source of truth)
│   ├── templates/              # HTML templates for PDF rendering
│   └── known_skills.json       # Approved skill additions (safe/careful/never)
│
├── dashboard/
│   ├── backend/                # FastAPI REST API
│   │   ├── main.py            # App entry point + CORS
│   │   ├── db.py              # MySQL connection pooling
│   │   └── routers/           # Endpoint modules
│   └── frontend/              # React + TypeScript + Vite
│       └── src/
│           ├── pages/         # JobsPage, JobDetail, JobsTable
│           └── components/    # StatsBar, shared UI
│
├── config.py                   # Centralized configuration
├── docker-compose.yml          # MySQL 8.0 service
└── output_cvs/                 # Generated PDF output
```

---

## Pipeline

### Data Flow

```
SCRAPE (2–5 min)          SCORE (3 min/100 jobs)       TAILOR (5 min/50 jobs)
  JustJoinIT API ─┐         DeepSeek API ──→             DeepSeek API ──→
  NoFluffJobs UI ─┘         fit_score (0–100)            title + summary
  status: 'new'             cv_variant (crp/igm)         skill reordering
                            status: 'scored'              status: 'tailored'

GENERATE PDF (1 min/10)   APPLY (manual)
  Headless Chrome ──→       Open URL + attach PDF
  output_cvs/*.pdf
  status: 'pdf_ready'       status: 'applied'
```

### Scoring Rubric

The AI scorer applies a seniority-gated ceiling before evaluating tech fit:

| Role Level | Score Ceiling |
|---|---|
| Lead / Principal | 45 |
| Senior | 70 |
| Mid | 85 |
| Junior | 100 |

Nice-to-have skills add +3 each (max +10). Hard blockers (niche platforms) cap at 25.

### Dual CV System

| Variant | File | Use Case |
|---|---|---|
| `crp` (Corporate) | `master_cv_crp.md` | Banks, insurance, Big4, traditional enterprise |
| `igm` (iGaming) | `master_cv_igm.md` | Startups, fintech, iGaming, crypto-adjacent |

The AI scorer classifies each job into a variant based on company type and industry. The pipeline then uses the matching master CV and HTML template for tailoring and PDF generation.

### Tailoring Safety

CV tailoring follows strict no-fabrication rules:

- **Title & summary:** Rewritten per job via LLM
- **Skills:** Reordered programmatically; additions only from `known_skills.json`
  - `safe` — always allowed
  - `careful` — only if job explicitly requires
  - `never` — forbidden (not on actual CV)
- **Experience & projects:** Never modified

---

## API

The dashboard backend exposes REST endpoints on port 8001:

| Endpoint | Method | Description |
|---|---|---|
| `/jobs` | GET | List jobs (filter by status, source, min_score, search) |
| `/jobs/{id}/{source}` | GET | Get single job details |
| `/jobs/{id}/{source}` | PATCH | Update job fields |
| `/stats` | GET | Job counts by status |
| `/actions/scrape` | POST | Trigger scraping (SSE stream) |
| `/actions/score` | POST | Trigger scoring (SSE stream) |
| `/actions/tailor` | POST | Trigger tailoring (SSE stream) |
| `/actions/generate-pdf-batch` | POST | Trigger PDF generation (SSE stream) |
| `/jobs/{id}/{source}/pdf` | GET | Download generated PDF |

Action endpoints use Server-Sent Events for real-time log streaming.

---

## Database

MySQL 8.0 via Docker Compose. Primary table: `jobs` with composite key `(id, source)`.

**Status flow:** `new` → `scored` → `tailored` → `pdf_ready` → `applied`

| Column | Type | Description |
|---|---|---|
| `id` | VARCHAR(255) | Job ID from source platform |
| `source` | VARCHAR(50) | `justjoinit` or `nofluffjobs` |
| `position` | VARCHAR(255) | Job title |
| `company` | VARCHAR(255) | Company name |
| `fit_score` | TINYINT | AI-calculated fit score (0–100) |
| `cv_variant` | VARCHAR(3) | `crp` or `igm` |
| `tailored_cv` | TEXT | JSON: `{title, summary, skills_html}` |
| `status` | VARCHAR(50) | Current pipeline stage |
| `url` | VARCHAR(500) | Original posting URL (unique) |
