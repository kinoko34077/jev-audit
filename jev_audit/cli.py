from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .auditor import (
    DEFAULT_MAX_BATCHES,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_TOTAL_CHARS,
    MAX_WORKERS,
)
from .profiles import available_profiles
from .reporting import format_report, write_json
from .runtime_bridge import run_audit


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jev-audit",
        description="Fast probabilistic directory audit powered by TypeSafe AI Jev.",
    )
    parser.add_argument("path", nargs="?", default=".", help="directory to audit (default: current directory)")
    parser.add_argument("--profile", default="development", help="bundled profile name or JSON file path")
    parser.add_argument("--changed-only", action="store_true", help="audit only Git changed/untracked files")
    parser.add_argument("--base-ref", help="compare explicit base commit to HEAD; requires --changed-only")
    parser.add_argument("--max-file-chars", type=int, default=12_000)
    parser.add_argument("--max-file-bytes", type=int, default=2_000_000)
    parser.add_argument("--batch-chars", type=int, default=32_000)
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help=f"parallel Jev batch requests (maximum {MAX_WORKERS})",
    )
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    parser.add_argument("--max-total-chars", type=int, default=DEFAULT_MAX_TOTAL_CHARS)
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES)
    parser.add_argument(
        "--model",
        help="Jev model name (default: pinned jev-1.13.0; TYPESAFE_DEFAULT_MODEL overrides it)",
    )
    parser.add_argument("--json", action="store_true", help="print JSON only")
    parser.add_argument("--save", type=Path, help="save full report JSON")
    parser.add_argument(
        "--fail-on",
        choices=("never", "review", "rework"),
        default="never",
        help="nonzero exit threshold for CI",
    )
    parser.add_argument("--list-profiles", action="store_true")
    return parser


def _exit_code(status: str, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    if fail_on == "review":
        return 1 if status in {"review", "rework", "unknown"} else 0
    if fail_on == "rework":
        return 1 if status == "rework" else 0
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.list_profiles:
        for name in available_profiles():
            print(name)
        return 0

    try:
        report = run_audit(
            args.path,
            profile=args.profile,
            changed_only=args.changed_only,
            base_ref=args.base_ref,
            max_file_chars=args.max_file_chars,
            max_file_bytes=args.max_file_bytes,
            batch_chars=args.batch_chars,
            workers=args.workers,
            model=args.model,
            max_files=args.max_files,
            max_total_chars=args.max_total_chars,
            max_batches=args.max_batches,
        )
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.save:
        try:
            write_json(report, args.save)
        except Exception as exc:
            print(f"ERROR: could not save report: {exc}", file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))

    return _exit_code(report.status, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
