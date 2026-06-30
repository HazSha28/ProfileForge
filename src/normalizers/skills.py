"""
src/normalizers/skills.py
-------------------------
WHY THIS FILE EXISTS
-------------------------
Skills written by candidates are wildly inconsistent: "JS", "javascript",
"java script", "node", "Node.js", "NodeJS" all refer to the same things.
This module maps known aliases to a single canonical name so that skill
matching and deduplication work correctly downstream.

PIPELINE CONNECTION
-------------------
  Called by the Merger after parsing.
  Input:  list of raw skill strings from CandidateRecord
  Output: deduplicated list of canonical skill strings
"""

from __future__ import annotations

from typing import Optional

from src.utils.helpers import get_logger, safe_strip

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Skill alias map
# ---------------------------------------------------------------------------
# WHY: A dictionary keyed by lowercase alias pointing to the canonical name.
# Using lowercase keys means lookups are always case-insensitive — we just
# call `.lower()` on the input before checking the map.
#
# HOW TO EXTEND: Add new entries here without touching any other code.
# The key is any alias (lowercase), the value is the canonical display name.
# ---------------------------------------------------------------------------
SKILL_ALIASES: dict[str, str] = {
    # ── JavaScript family ──────────────────────────────────────
    "js": "JavaScript", "javascript": "JavaScript",
    "java script": "JavaScript", "ecmascript": "JavaScript",
    "es6": "JavaScript", "es2015": "JavaScript",

    # ── TypeScript ─────────────────────────────────────────────
    "ts": "TypeScript", "typescript": "TypeScript",

    # ── Python ─────────────────────────────────────────────────
    "python": "Python", "python3": "Python", "py": "Python",

    # ── Java ───────────────────────────────────────────────────
    "java": "Java",

    # ── C family ───────────────────────────────────────────────
    "c": "C", "c programming": "C",
    "c++": "C++", "cpp": "C++",
    "c#": "C#", "csharp": "C#", "c sharp": "C#",

    # ── Web frameworks ─────────────────────────────────────────
    "node": "Node.js", "nodejs": "Node.js", "node.js": "Node.js",
    "react": "React", "reactjs": "React", "react.js": "React",
    "vue": "Vue.js", "vuejs": "Vue.js", "vue.js": "Vue.js",
    "angular": "Angular", "angularjs": "Angular",
    "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
    "spring": "Spring", "spring boot": "Spring Boot",
    "express": "Express.js", "express.js": "Express.js",
    "next.js": "Next.js", "nextjs": "Next.js",

    # ── Mobile ─────────────────────────────────────────────────
    "kotlin": "Kotlin", "swift": "Swift",
    "flutter": "Flutter", "react native": "React Native",
    "android": "Android", "ios": "iOS",

    # ── Databases ──────────────────────────────────────────────
    "sql": "SQL", "mysql": "MySQL",
    "postgresql": "PostgreSQL", "postgres": "PostgreSQL",
    "mongo": "MongoDB", "mongodb": "MongoDB",
    "redis": "Redis", "sqlite": "SQLite",
    "oracle": "Oracle DB", "cassandra": "Cassandra",
    "elasticsearch": "Elasticsearch",

    # ── Cloud ──────────────────────────────────────────────────
    "aws": "AWS", "amazon web services": "AWS",
    "gcp": "GCP", "google cloud": "GCP", "google cloud platform": "GCP",
    "azure": "Azure", "microsoft azure": "Azure",

    # ── DevOps / Infra ─────────────────────────────────────────
    "docker": "Docker", "kubernetes": "Kubernetes", "k8s": "Kubernetes",
    "ci/cd": "CI/CD", "cicd": "CI/CD",
    "jenkins": "Jenkins", "github actions": "GitHub Actions",
    "terraform": "Terraform", "ansible": "Ansible",
    "linux": "Linux", "unix": "Unix", "bash": "Bash",
    "nginx": "Nginx", "apache": "Apache",

    # ── AI / ML / Data ─────────────────────────────────────────
    "ml": "Machine Learning", "machine learning": "Machine Learning",
    "deep learning": "Deep Learning", "dl": "Deep Learning",
    "ai": "Artificial Intelligence", "artificial intelligence": "Artificial Intelligence",
    "nlp": "NLP", "natural language processing": "NLP",
    "computer vision": "Computer Vision", "cv": "Computer Vision",
    "data science": "Data Science", "data analysis": "Data Analysis",
    "data analytics": "Data Analytics",
    "pandas": "Pandas", "numpy": "NumPy",
    "scikit-learn": "scikit-learn", "sklearn": "scikit-learn",
    "tensorflow": "TensorFlow", "keras": "Keras", "pytorch": "PyTorch",
    "matplotlib": "Matplotlib", "seaborn": "Seaborn",
    "tableau": "Tableau", "power bi": "Power BI",

    # ── APIs / Architecture ────────────────────────────────────
    "rest": "REST APIs", "rest api": "REST APIs", "restful": "REST APIs",
    "graphql": "GraphQL", "api": "API Development",    "microservices": "Microservices", "soap": "SOAP",

    # ── Web fundamentals ───────────────────────────────────────
    "html": "HTML", "html5": "HTML",
    "css": "CSS", "css3": "CSS",
    "sass": "Sass", "scss": "Sass",
    "bootstrap": "Bootstrap", "tailwind": "Tailwind CSS",
    "tailwind css": "Tailwind CSS",

    # ── Version control / Tools ────────────────────────────────
    "git": "Git", "github": "GitHub", "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "jira": "Jira", "confluence": "Confluence",
    "postman": "Postman", "swagger": "Swagger",
    "vs code": "VS Code", "vscode": "VS Code",
    "intellij": "IntelliJ IDEA",

    # ── Other languages ────────────────────────────────────────
    "go": "Go", "golang": "Go",
    "rust": "Rust", "ruby": "Ruby", "rails": "Ruby on Rails",
    "php": "PHP", "scala": "Scala",
    "r": "R", "matlab": "MATLAB",

    # ── Soft Skills ────────────────────────────────────────────
    "communication": "Communication",
    "verbal communication": "Communication",
    "written communication": "Communication",
    "leadership": "Leadership",
    "team leadership": "Leadership",
    "teamwork": "Teamwork",
    "team player": "Teamwork",
    "collaboration": "Collaboration",
    "problem solving": "Problem Solving",
    "problem-solving": "Problem Solving",
    "critical thinking": "Critical Thinking",
    "analytical thinking": "Analytical Thinking",
    "analytical skills": "Analytical Thinking",
    "time management": "Time Management",
    "project management": "Project Management",
    "adaptability": "Adaptability",
    "adaptable": "Adaptability",
    "creativity": "Creativity",
    "creative thinking": "Creativity",
    "attention to detail": "Attention to Detail",
    "detail oriented": "Attention to Detail",
    "decision making": "Decision Making",
    "decision-making": "Decision Making",
    "multitasking": "Multitasking",
    "organisational skills": "Organisational Skills",
    "organizational skills": "Organisational Skills",
    "presentation skills": "Presentation Skills",
    "public speaking": "Public Speaking",
    "interpersonal skills": "Interpersonal Skills",
    "negotiation": "Negotiation",
    "conflict resolution": "Conflict Resolution",
    "mentoring": "Mentoring",
    "coaching": "Coaching",
    "research": "Research",
    "self motivated": "Self-motivated",
    "self-motivated": "Self-motivated",
    "initiative": "Initiative",
    "work ethic": "Work Ethic",
    "fast learner": "Quick Learner",
    "quick learner": "Quick Learner",

    # ── Extracurricular / Activities ───────────────────────────
    "event management": "Event Management",
    "event organizer": "Event Management",
    "volunteer": "Volunteering",
    "volunteering": "Volunteering",
    "community service": "Community Service",
    "nss": "NSS",
    "ncc": "NCC",
    "sports": "Sports",
    "athletics": "Athletics",
    "debate": "Debate",
    "quiz": "Quiz",
    "hackathon": "Hackathon Participation",
    "hackathons": "Hackathon Participation",
    "open source": "Open Source Contribution",
    "open source contribution": "Open Source Contribution",
    "blogging": "Technical Blogging",
    "technical writing": "Technical Writing",
}


def normalize_skill(raw: Optional[str]) -> Optional[str]:
    """
    Map a single raw skill string to its canonical name.

    Args:
        raw: Raw skill string (e.g. "JS", "java script", "  Python  ").

    Returns:
        Canonical skill name or title-cased original if no alias found.
        Returns None if input is blank.

    Examples:
        normalize_skill("JS")          -> "JavaScript"
        normalize_skill("java script") -> "JavaScript"
        normalize_skill("Kubernetes")  -> "Kubernetes"
        normalize_skill("  ")          -> None
    """
    cleaned = safe_strip(raw)
    if not cleaned:
        return None

    # CONCEPT — dict.get(key, default):
    #   Returns the value for `key` if it exists, otherwise returns `default`.
    #   Here, if the skill has no alias we fall back to title-casing the
    #   original input so it still looks presentable in output.
    canonical = SKILL_ALIASES.get(cleaned.lower())
    if canonical:
        return canonical

    # No alias found — preserve original casing if it contains uppercase
    # (e.g. "REST APIs" should stay "REST APIs", not become "Rest Apis")
    # Only title-case if the original is all-lowercase
    if cleaned == cleaned.lower():
        return cleaned.title()
    return cleaned


def normalize_skills(raw_list: list[str]) -> list[str]:
    """
    Normalize a list of raw skill strings and deduplicate.

    Args:
        raw_list: List of raw skill strings from a parser.

    Returns:
        Ordered, deduplicated list of canonical skill names.

    Example:
        normalize_skills(["JS", "python", "JavaScript", "Python"])
        -> ["JavaScript", "Python"]
    """
    seen: set[str] = set()
    result: list[str] = []

    for raw in raw_list:
        normalised = normalize_skill(raw)
        if normalised and normalised not in seen:
            seen.add(normalised)
            result.append(normalised)

    return result
