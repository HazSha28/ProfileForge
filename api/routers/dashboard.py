"""
api/routers/dashboard.py
-------------------------
Dashboard metrics endpoint.
In production this would query a database. For the internship demo,
we return realistic mock data that matches the UI.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["Dashboard"])


@router.get("/stats")
async def get_stats():
    """Return dashboard statistics."""
    return {
        "total_processed":   142,
        "processed_today":    17,
        "avg_confidence":    0.82,
        "sources_breakdown": {
            "csv_only":         23,
            "pdf_only":         18,
            "csv_and_pdf":      89,
            "all_three":        12,
        },
        "recent_candidates": [
            {"name": "Jane Doe",       "confidence": 0.85, "sources": ["Resume", "CSV"], "time": "2 min ago"},
            {"name": "Michael Chen",   "confidence": 0.90, "sources": ["Resume", "CSV", "ATS"], "time": "15 min ago"},
            {"name": "Priya Sharma",   "confidence": 0.60, "sources": ["Resume"], "time": "1 hr ago"},
            {"name": "Alex Johnson",   "confidence": 0.85, "sources": ["Resume", "CSV"], "time": "3 hr ago"},
        ],
        "top_skills": [
            "Python", "JavaScript", "React", "SQL", "Docker",
            "TypeScript", "AWS", "Node.js", "PostgreSQL", "Kubernetes"
        ],
    }
