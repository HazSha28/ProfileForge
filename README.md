# ProfileForge

**Multi-Source Candidate Data Transformer**

> Unify. Normalise. Score. Deploy.

ProfileForge is a production-quality HR-Tech SaaS application that transforms scattered candidate data from multiple sources into a single validated, scored, and canonical JSON profile — with full provenance tracking on every field.

---

## Features

| Feature | Details |
|---|---|
| **Single Candidate** | Upload CSV + PDF → one canonical profile |
| **Bulk Processing** | Upload recruiter CSV + ZIP of resumes → batch profiles |
| **AI-powered extraction** | Google Gemini 1.5 Flash extracts structured data from unstructured PDFs |
| **Resume matching** | Deterministic engine: Email → Phone → Reg Number → GitHub → Name → Fuzzy (RapidFuzz 90%) |
| **Skills extraction** | Technical + soft skills + extracurricular activities |
| **Phone normalisation** | All formats → E.164 (supports Indian, US, international) |
| **Provenance tracking** | Every field records which source(s) contributed |
| **Confidence scoring** | 0.5 (single) → 0.85 (dual) → 1.0 (triple-verified) |
| **OAuth authentication** | Google + GitHub sign-in via Authlib |
| **Live SSE progress** | Real-time pipeline stream — stage by stage |
| **Profile History** | Search, filter, sort, re-open, download all processed profiles |
| **Bulk History** | Per-candidate results table with match method and confidence |
| **Dashboard Analytics** | Matched / Missing / Standalone / Failed stats after bulk jobs |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + Uvicorn (ASGI, async) |
| Templates | Jinja2 |
| Data Models | Pydantic v2 |
| PDF Parsing | pdfplumber + PyMuPDF (fitz) for embedded links |
| Phone Normalisation | phonenumbers (Google libphonenumber) |
| Fuzzy Matching | RapidFuzz (token_set_ratio) |
| Country Codes | pycountry (ISO Alpha-2) |
| Date Parsing | python-dateutil |
| AI Extraction | Google Gemini 1.5 Flash |
| Auth | Authlib (Google OAuth 2.0 + GitHub OAuth 2.0) |
| Sessions | Starlette SessionMiddleware (signed cookies) |
| Frontend | Vanilla HTML / CSS / JavaScript (no framework) |

---

## Project Structure

```
ProfileForge/
├── server.py                  # FastAPI entry point
├── main.py                    # CLI entry point
├── Procfile                   # Render.com deploy config
├── render.yaml                # Render.com service definition
├── requirements.txt
├── api/
│   └── routes/
│       ├── pages.py           # HTML page routes
│       ├── pipeline.py        # Single-candidate API + SSE
│       ├── bulk.py            # Bulk processing API + SSE
│       └── oauth.py           # Google + GitHub OAuth
├── src/
│   ├── bulk/
│   │   ├── bulk_matcher.py    # Resume matching engine
│   │   └── bulk_processor.py  # Bulk orchestration layer
│   ├── parsers/
│   │   ├── csv_parser.py      # Recruiter CSV parser
│   │   ├── resume_parser.py   # PDF text + skills extractor
│   │   └── ai_resume_parser.py # Gemini AI extraction
│   ├── normalizers/
│   │   ├── phone.py           # E.164 phone normalisation
│   │   ├── email.py           # Email normalisation
│   │   ├── skills.py          # 130+ skill aliases (tech + soft + extracurricular)
│   │   ├── location.py        # ISO Alpha-2 country normalisation
│   │   └── dates.py           # ISO 8601 date normalisation
│   ├── merger/merge.py        # Multi-source merge engine
│   ├── confidence/confidence.py # Deterministic scoring
│   ├── projection/projector.py  # Output field projection
│   ├── validator/validator.py   # Schema validation
│   ├── services/pipeline.py     # Single-candidate orchestration
│   └── models/schema.py         # Pydantic data models
├── web/
│   ├── templates/             # Jinja2 HTML templates
│   │   ├── base.html          # Sidebar shell (collapsible)
│   │   ├── dashboard.html     # Main dashboard + bulk stats
│   │   ├── candidate.html     # Single upload form
│   │   ├── bulk.html          # Bulk upload form
│   │   ├── bulk_progress.html # Live SSE progress view
│   │   ├── bulk_history.html  # Bulk results table
│   │   ├── history.html       # Single profile history
│   │   └── profile.html       # Profile viewer
│   └── static/css / js /img
├── input/                     # Sample CSV + config
└── output/                    # Generated JSON profiles
```

---

## Setup

### 1. Clone

```bash
git clone https://github.com/HazSha28/ProfileForge.git
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

Fill in `.env`:

| Variable | Where to get it |
|---|---|
| `FLASK_SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_CLIENT_ID` | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console |
| `GITHUB_CLIENT_ID` | [GitHub Developer Settings](https://github.com/settings/developers) |
| `GITHUB_CLIENT_SECRET` | GitHub Developer Settings |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) (free) |

### 4. Run

```bash
python server.py
```

- App: **http://127.0.0.1:8000**
- API docs: **http://127.0.0.1:8000/docs**

---

## Pages

| URL | Description |
|---|---|
| `/dashboard` | Landing page — stats, bulk job results, activity feed |
| `/candidate` | Single candidate upload (CSV + PDF) |
| `/profile` | View generated profile |
| `/bulk` | Bulk upload (CSV + ZIP of resumes) |
| `/bulk/progress` | Live processing progress stream |
| `/bulk/history` | All bulk job results — search, filter, download |
| `/history` | Single profile history |
| `/login` | Google / GitHub OAuth sign-in |
| `/help` | Full documentation |
| `/docs` | FastAPI Swagger UI |

---

## Bulk Processing

### How it works

1. Upload a **recruiter CSV** with one row per candidate
2. Upload a **ZIP** containing all resume PDFs (named with candidate info)
3. ProfileForge **matches** each CSV row to a resume using:
   - Email in resume filename or PDF content
   - Phone number (E.164 normalised, last-10-digit match)
   - Registration/roll number in filename (e.g. `711523BCB041`)
   - GitHub username from the GitHub URL column
   - Exact normalised name match
   - RapidFuzz fuzzy name match (≥90% token_set_ratio)
4. Each matched pair runs the **full pipeline** (parse → merge → validate → project)
5. Results saved as `output/bulk_<job_id>/candidate_NNN.json` + `bulk_summary.json`

### Supported CSV columns (flexible, case-insensitive)

| Field | Accepted column names |
|---|---|
| Name | `Name of the Student`, `full_name`, `name`, `candidate_name` |
| Registration | `Registration Number`, `reg no`, `roll no` |
| Email | `email`, `email_address`, `e-mail` |
| Phone | `phone`, `mobile`, `telephone` |
| LinkedIn | `LinkedIn Profile Url`, `linkedin`, `linkedin_url` |
| GitHub | `Github Profile Url`, `github`, `github_url` |
| Resume | `Resume Drive Url`, `resume`, `cv url` |

### Resume filename conventions (best match rate)

| Format | Match method |
|---|---|
| `PRAKASH B-711523BCB041.pdf` | Registration number |
| `john.doe@email.com_resume.pdf` | Email |
| `+919876543210_cv.pdf` | Phone |
| `prakashb96_resume.pdf` | GitHub username |
| `John_Doe_Resume.pdf` | Name (exact/fuzzy) |

---

## Phone Number Formats Supported

```
9876543210         → +919876543210  (with IN hint)
+91 9876543210     → +919876543210
+91-9876543210     → +919876543210
(+91)9876543210    → +919876543210
91 9876543210      → +919876543210
(415) 555-2671     → +14155552671  (with US hint)
+44 20 7946 0958   → +442079460958
```

---

## Skills Coverage

The normaliser covers **130+ aliases** across three categories:

- **Technical**: JavaScript, TypeScript, Python, Java, React, Node.js, Django, Flask, FastAPI, Docker, Kubernetes, AWS, GCP, Azure, TensorFlow, PyTorch, PostgreSQL, MongoDB, Redis, Git, Next.js, Tailwind CSS, and more
- **Soft skills**: Communication, Leadership, Teamwork, Problem Solving, Time Management, Public Speaking, Critical Thinking, Adaptability, and more
- **Extracurricular**: Event Management, Volunteering, NSS, NCC, Hackathon Participation, Open Source Contribution, Technical Writing, and more

---

## Merge Policy

| Field type | Rule |
|---|---|
| Scalar (name, headline, years) | Resume wins over CSV |
| Lists (emails, phones, skills) | Deduplicated union of all sources |
| Nested (location, links) | Each sub-field merged independently |
| Missing in all sources | `null` |

---

## Confidence Scores

| Sources | Score |
|---|---|
| CSV only | 0.5 |
| Resume only | 0.6 |
| Resume + CSV | 0.85 |
| Resume + CSV + LinkedIn | 1.0 |

---

## Deploy on Render.com

The `render.yaml` and `Procfile` are included. Steps:

1. Push to GitHub
2. Go to [render.com](https://render.com) → New → Web Service → connect repo
3. Add env vars in Render dashboard (same as `.env`)
4. Deploy — takes ~3 minutes
5. Add `https://your-app.onrender.com/auth/google/callback` to Google OAuth authorised redirect URIs
6. Add same for GitHub OAuth callback URL

---

## License

MIT License
