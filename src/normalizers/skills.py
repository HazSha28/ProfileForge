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
    # JavaScript family
    "js": "JavaScript",
    "javascript": "JavaScript",
    "java script": "JavaScript",
    "ecmascript": "JavaScript",
    "es6": "JavaScript",
    "es2015": "JavaScript",

    # TypeScript
    "ts": "TypeScript",
    "typescript": "TypeScript",

    # Python
    "python": "Python",
    "python3": "Python",
    "py": "Python",

    # Java
    "java": "Java",

    # Node.js
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",

    # React
    "react": "React",
    "reactjs": "React",
    "react.js": "React",

    # Vue
    "vue": "Vue.js",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",

    # SQL / Databases
    "sql": "SQL",
    "mysql": "MySQL",
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",

    # Cloud
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "azure": "Azure",
    "microsoft azure": "Azure",

    # Containers / DevOps
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",

    # Machine Learning / Data
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",

    # Other common skills
    "git": "Git",
    "github": "Git",         # normalise as the tool, not the platform
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "restful": "REST APIs",
    "graphql": "GraphQL",
    "html": "HTML",
    "css": "CSS",
    "c#": "C#",
    "csharp": "C#",
    "c++": "C++",
    "cpp": "C++",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "r": "R",
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

    # No alias found — return title-cased original
    logger.debug("No canonical alias for skill %r, keeping as-is (title-cased)", cleaned)
    return cleaned.title()


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
