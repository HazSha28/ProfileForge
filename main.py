"""
main.py
-------
WHY THIS FILE EXISTS
--------------------
This is the single entry point for the application. It:
  1. Parses CLI arguments.
  2. Calls each pipeline stage in order.
  3. Handles all errors gracefully — no unhandled exceptions reach the user.
  4. Writes the final JSON output file.

PIPELINE ORDER
--------------
  CLI args
    → CSV Parser    → CandidateRecord
    → Resume Parser → CandidateRecord
    → Merger        → CanonicalProfile   (normalisation happens inside)
    → Validator     → (CanonicalProfile, warnings)
    → Projector     → dict
    → JSON file

CONCEPT — if __name__ == "__main__":
    Python sets __name__ to "__main__" only when the file is run directly
    (e.g. `python main.py`). When another module imports main.py, __name__
    is "main" instead. This guard ensures the CLI only runs when called
    directly, not when imported (e.g. during testing).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.merger.merge import merge
from src.parsers.csv_parser import ParseError, parse as parse_csv
from src.parsers.resume_parser import parse as parse_resume
from src.projection.projector import load_config, project
from src.utils.helpers import get_logger
from src.validator.validator import validate

logger = get_logger("profileforge")


# ---------------------------------------------------------------------------
# CLI argument parser
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    """
    Define and return the CLI argument parser.

    CONCEPT — argparse:
        argparse is Python's standard library module for building CLIs.
        It handles --flag syntax, type validation, help text, and error
        messages automatically. You define what arguments exist; argparse
        does the parsing.
    """
    parser = argparse.ArgumentParser(
        prog="profileforge",
        description=(
            "ProfileForge — Multi-Source Candidate Data Transformer\n"
            "Merges a recruiter CSV and a resume PDF into a canonical candidate profile."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--csv",
        required=True,
        metavar="PATH",
        help="Path to the recruiter CSV file (required).",
    )
    parser.add_argument(
        "--resume",
        required=True,
        metavar="PATH",
        help="Path to the resume PDF file (required).",
    )
    parser.add_argument(
        "--config",
        required=False,
        default=None,
        metavar="PATH",
        help="Path to the projection config JSON file (optional).",
    )
    parser.add_argument(
        "--output",
        required=False,
        default="output/candidate.json",
        metavar="PATH",
        help="Output path for the canonical profile JSON (default: output/candidate.json).",
    )

    return parser


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(csv_path: str, resume_path: str, config_path: str, output_path: str) -> int:
    """
    Execute the full ETL pipeline and write the output file.

    Returns:
        0 on success, 1 on any failure.
    """

    # ── Stage 1: Parse ──────────────────────────────────────────────────────
    logger.info("── Stage 1: Parsing sources ──")

    try:
        csv_record = parse_csv(csv_path)
    except ParseError as exc:
        logger.error("CSV parsing failed: %s", exc)
        return 1

    try:
        resume_record = parse_resume(resume_path)
    except ParseError as exc:
        logger.error("Resume parsing failed: %s", exc)
        return 1

    # ── Stage 2: Merge (includes normalisation) ─────────────────────────────
    logger.info("── Stage 2: Merging and normalising ──")
    try:
        profile = merge([csv_record, resume_record])
    except Exception as exc:
        logger.error("Merge failed unexpectedly: %s", exc)
        return 1

    # ── Stage 3: Validate ───────────────────────────────────────────────────
    logger.info("── Stage 3: Validating ──")
    try:
        profile, warnings = validate(profile)
        if warnings:
            logger.warning("Validation produced %d warning(s):", len(warnings))
            for w in warnings:
                logger.warning("  • %s", w)
    except Exception as exc:
        logger.error("Validation failed unexpectedly: %s", exc)
        return 1

    # ── Stage 4: Project ────────────────────────────────────────────────────
    logger.info("── Stage 4: Applying output projection ──")
    try:
        config = load_config(config_path)
        output_dict = project(profile, config)
    except Exception as exc:
        logger.error("Projection failed unexpectedly: %s", exc)
        return 1

    # ── Stage 5: Write output ───────────────────────────────────────────────
    logger.info("── Stage 5: Writing output ──")
    try:
        _write_output(output_dict, output_path)
    except OSError as exc:
        logger.error("Failed to write output file: %s", exc)
        return 1

    logger.info("✓ Done. Output written to: %s", output_path)
    return 0


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

def _write_output(data: dict, output_path: str) -> None:
    """
    Write a dict to a UTF-8 JSON file, creating parent directories as needed.

    Args:
        data:        The dict to serialise.
        output_path: File path to write (e.g. "output/candidate.json").

    CONCEPT — Path.mkdir(parents=True, exist_ok=True):
        Creates the full directory tree if it doesn't exist.
        `exist_ok=True` means "don't raise an error if it already exists".
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        # indent=2 produces human-readable JSON with 2-space indentation
        # ensure_ascii=False preserves Unicode characters (accented names etc.)
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Output file size: %d bytes", path.stat().st_size)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    # Validate that input files actually exist before starting the pipeline
    for flag, path_str in [("--csv", args.csv), ("--resume", args.resume)]:
        if not Path(path_str).exists():
            logger.error("Input file for %s not found: %s", flag, path_str)
            sys.exit(1)

    exit_code = run_pipeline(
        csv_path=args.csv,
        resume_path=args.resume,
        config_path=args.config,
        output_path=args.output,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Last-resort catch — nothing should reach here, but if it does we
        # log it cleanly rather than printing a raw traceback.
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        sys.exit(1)
