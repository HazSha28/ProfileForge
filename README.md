# ProfileForge

**Multi-Source Candidate Data Transformer**

> Unify. Transform. Empower Talent.

ProfileForge is a production-quality HR-Tech SaaS application that combines candidate information from multiple heterogeneous sources into a single, validated, canonical profile — with full provenance tracking and deterministic confidence scoring on every field.

---

## Features

- **Multi-source ingestion** — Recruiter CSV + Resume PDF + Platform links
- **AI-powered extraction** — Google Gemini extracts structured data from unstructured PDF resumes
- **Deterministic pipeline** — Parse → Normalise → Merge → Confidence → Validate → Project
- **Provenance tracking** — every field records which sources contributed to it
- **Confidence scoring** — 0.5 (single source) → 0.85 (dual) → 1.0 (triple verified)
- **Configurable output** — include/exclude/rename fields via `config.json`
- **OAuth authentication** — Google and GitHub sign-in
- **Live pipeline progress** — real-time SSE stream showing each stage
- **Professional dashboard** — SaaS-grade UI with sidebar navigation

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| Templates | Jinja2 |
| Data Models | Pydantic v2 |
| PDF Parsing | pdfplumber |
| Phone Normalisation | phonenumbers (libphonenumber) |
| Country Codes | pycountry (ISO Alpha-2) |
| Date Parsing | python-dateutil |
| AI Extraction | Google Gemini 1.5 Flash |
| Auth | Authlib (Google OAuth + GitHub OAuth) |
| Sessions | Starlette SessionMiddleware |

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/your-username/ProfileForge.git
cd ProfileForge
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:
- **FLASK_SECRET_KEY** — generate with `python -c "import secrets; print(secrets.token_hex(32))"`
- **GOOGLE_CLIENT_ID / SECRET** — from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
- **GITHUB_CLIENT_ID / SECRET** — from [GitHub Developer Settings](https://github.com/settings/developers)
- **GEMINI_API_KEY** — from [Google AI Studio](https://aistudio.google.com/app/apikey) (free)

### 4. Run

```bash
python server.py
```

Open **http://127.0.0.1:8000**

API docs at **http://127.0.0.1:8000/docs**

---

## CLI Usage

The pipeline also runs as a standalone CLI:

```bash
python main.py \
  --csv input/recruiter.csv \
  --resume input/resume.pdf \
  --config input/config.json
```

Output: `output/candidate.json`

---

## Project Structure

```
ProfileForge/
├── server.py              # FastAPI app entry point
├── main.py                # CLI entry point
├── auth_oauth.py          # Legacy Flask OAuth (superseded)
├── api/
│   └── routes/
│       ├── pages.py       # HTML page routes
│       ├── pipeline.py    # API endpoints + SSE stream
│       └── oauth.py       # Google + GitHub OAuth
├── src/
│   ├── parsers/           # CSV parser, PDF parser, AI parser
│   ├── normalizers/       # Email, phone, skills, dates, location
│   ├── merger/            # Multi-source merge engine
│   ├── confidence/        # Confidence scoring
│   ├── projection/        # Output field projection
│   ├── validator/         # Schema validation
│   ├── models/            # Pydantic data models
│   └── utils/             # Logging, helpers
├── web/
│   ├── templates/         # Jinja2 HTML templates
│   └── static/            # CSS, JS, images
├── input/                 # Sample input files
├── .env.example           # Environment variable template
└── requirements.txt
```

---

## Pages

| URL | Description |
|---|---|
| `/dashboard` | Main dashboard (default landing page) |
| `/candidate` | Upload CSV + PDF, run pipeline |
| `/profile` | View generated canonical profile |
| `/login` | Sign in / Sign up |
| `/help` | Full documentation |
| `/terms` | Terms of Service |
| `/privacy` | Privacy Policy |
| `/docs` | FastAPI Swagger UI |

---

## Merge Policy

| Scenario | Rule |
|---|---|
| Same field, multiple sources | Resume wins over CSV |
| Timestamps available | Newest timestamp wins |
| List fields (emails, skills) | Deduplicated union of all sources |
| Field missing in all sources | `null` |

---

## Confidence Scores

| Sources | Score |
|---|---|
| CSV only | 0.5 |
| Resume only | 0.6 |
| Resume + CSV | 0.85 |
| Resume + CSV + LinkedIn | 1.0 |

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*Built as an Eightfold Engineering Internship Assignment.*
