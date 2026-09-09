"""Export one test run's Allure results to BigQuery.

Runs after pytest in CI. Reads the raw Allure results, normalizes them into one
row per test, and appends them to an append-only table that the BI dashboards
read.

**This is Phase 7 only.** Nothing in the core test suite imports it, and
google-cloud-bigquery is not in the project's requirements.txt - it lives in
analytics/requirements.txt so the suite never depends on a cloud SDK to run.

Usage
-----
    # Parse and print what would be uploaded; needs no credentials at all.
    python analytics/export_to_bigquery.py --dry-run

    # Parse and append to BigQuery.
    python analytics/export_to_bigquery.py

Configuration comes from the environment (see .env.example):
    BQ_PROJECT, BQ_DATASET, BQ_TABLE, GOOGLE_APPLICATION_CREDENTIALS

Security note: the credential used here needs only ``bigquery.dataEditor`` on
this single table. The dashboard reads with a *separate*, read-only credential.
See ARCHITECTURE.md section 6.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "reports" / "allure-results"
SCHEMA_PATH = Path(__file__).resolve().parent / "bq_schema.json"

# Allure statuses map onto ours. "broken" is an error rather than an assertion
# failure, but for trend purposes both mean the test did not pass, and a
# dashboard that separated them would just split one line into two.
STATUS_MAP = {
    "passed": "passed",
    "failed": "failed",
    "broken": "failed",
    "skipped": "skipped",
    "unknown": "failed",
}


@dataclass(frozen=True)
class TestRunRecord:
    """One row of the test_runs table."""

    run_id: str
    test_name: str
    suite: str
    status: str
    duration_seconds: float
    run_timestamp: str
    branch: str | None
    commit_sha: str | None
    retry_count: int
    marker: str | None


def _label(result: dict[str, Any], name: str) -> str | None:
    for label in result.get("labels", []):
        if label.get("name") == name:
            return label.get("value")
    return None


def _suite_of(result: dict[str, Any]) -> str:
    """ui, api or environment, from Allure's parentSuite label.

    parentSuite is "tests.ui" / "tests.api"; the environment checks sit
    directly under "tests".
    """
    parent = _label(result, "parentSuite") or ""
    if parent.endswith(".ui"):
        return "ui"
    if parent.endswith(".api"):
        return "api"
    return "environment"


def _marker_of(result: dict[str, Any]) -> str | None:
    """The pytest marker, which Allure records as a tag label."""
    for label in result.get("labels", []):
        if label.get("name") == "tag" and label.get("value") in {"smoke", "regression"}:
            return label.get("value")
    return None


def collapse_retries(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce a test's several attempts to one row, detecting flakiness.

    pytest-rerunfailures runs a failing test again, and Allure writes one result
    file per attempt. Uploaded raw, a single flaky test would look like one
    failure *and* one pass, which quietly corrupts every pass-rate figure the
    dashboards show.

    Attempts of the same test share a historyId, so they are grouped by it. If
    any attempt failed and the final one passed, that is the definition of
    flaky and the row is recorded as such. Duration is summed across attempts,
    because the wall-clock cost of a flaky test is what it actually cost the
    run.
    """
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        # Fall back to fullName when historyId is absent, so a malformed result
        # still becomes its own row rather than being silently merged.
        key = result.get("historyId") or result.get("fullName") or str(uuid.uuid4())
        grouped[key].append(result)

    collapsed: list[dict[str, Any]] = []
    for attempts in grouped.values():
        attempts.sort(key=lambda r: r.get("start", 0))
        final = attempts[-1]
        statuses = [STATUS_MAP.get(a.get("status", "unknown"), "failed") for a in attempts]
        final_status = statuses[-1]

        if len(attempts) > 1 and final_status == "passed" and "failed" in statuses:
            final_status = "flaky"

        total_ms = sum(max(a.get("stop", 0) - a.get("start", 0), 0) for a in attempts)

        collapsed.append(
            {
                "result": final,
                "status": final_status,
                "duration_ms": total_ms,
                "retry_count": len(attempts) - 1,
                "start": attempts[0].get("start", 0),
            }
        )
    return collapsed


def parse_allure_results(
    results_dir: Path,
    run_id: str,
    branch: str | None,
    commit_sha: str | None,
) -> list[TestRunRecord]:
    """Turn a directory of Allure results into rows ready for BigQuery."""
    raw: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*result.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                raw.append(json.load(handle))
        except (OSError, ValueError) as exc:
            # One unreadable file must not cost us the whole run's history.
            print(f"warning: skipping unreadable result {path.name}: {exc}", file=sys.stderr)

    records = []
    for entry in collapse_retries(raw):
        result = entry["result"]
        started = entry["start"]
        records.append(
            TestRunRecord(
                run_id=run_id,
                test_name=result.get("fullName") or result.get("name", "<unknown>"),
                suite=_suite_of(result),
                status=entry["status"],
                duration_seconds=round(entry["duration_ms"] / 1000, 3),
                # Allure records epoch milliseconds; BigQuery wants RFC 3339.
                run_timestamp=datetime.fromtimestamp(
                    started / 1000, tz=timezone.utc
                ).isoformat(),
                branch=branch,
                commit_sha=commit_sha,
                retry_count=entry["retry_count"],
                marker=_marker_of(result),
            )
        )
    return records


def write_jsonl(records: Iterable[TestRunRecord], destination: Path) -> int:
    """Write rows as newline-delimited JSON.

    Used by --dry-run, and as the fallback when an upload fails so a run's
    history can still be recovered and loaded later by hand.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record)) + "\n")
            count += 1
    return count


def upload_to_bigquery(records: list[TestRunRecord]) -> None:
    """Append rows to the configured BigQuery table.

    Imported lazily so --dry-run, and the whole core suite, work without the
    cloud SDK installed.
    """
    from google.cloud import bigquery  # noqa: PLC0415 - deliberately lazy

    project = os.environ["BQ_PROJECT"]
    dataset = os.environ["BQ_DATASET"]
    table = os.environ.get("BQ_TABLE", "test_runs")
    table_id = f"{project}.{dataset}.{table}"

    client = bigquery.Client(project=project)
    rows = [asdict(record) for record in records]

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise RuntimeError(f"BigQuery rejected {len(errors)} row(s): {errors[:3]}")
    print(f"appended {len(rows)} row(s) to {table_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Allure results directory (default: reports/allure-results)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and write JSONL locally instead of uploading. Needs no credentials.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "reports" / "test_runs.jsonl",
        help="Where --dry-run writes its rows",
    )
    args = parser.parse_args(argv)

    if not args.results_dir.is_dir():
        print(f"error: no such results directory: {args.results_dir}", file=sys.stderr)
        return 1

    # GitHub Actions supplies these; locally they fall back to sensible values.
    run_id = os.getenv("GITHUB_RUN_ID") or f"local-{uuid.uuid4().hex[:12]}"
    branch = os.getenv("GITHUB_REF_NAME")
    commit_sha = os.getenv("GITHUB_SHA")

    records = parse_allure_results(args.results_dir, run_id, branch, commit_sha)
    if not records:
        print(f"error: no results found in {args.results_dir}", file=sys.stderr)
        return 1

    summary: dict[str, int] = defaultdict(int)
    for record in records:
        summary[record.status] += 1
    print(
        f"run {run_id}: {len(records)} test(s) - "
        + ", ".join(f"{count} {status}" for status, count in sorted(summary.items()))
    )

    if args.dry_run:
        written = write_jsonl(records, args.out)
        print(f"dry run: wrote {written} row(s) to {args.out}")
        return 0

    try:
        upload_to_bigquery(records)
    except Exception as exc:
        # Never fail the build over analytics. The tests already ran and their
        # verdict is what matters; losing a history row is an inconvenience,
        # while a red build over a telemetry outage is a false alarm that
        # teaches people to ignore CI.
        fallback = args.out
        write_jsonl(records, fallback)
        print(
            f"warning: BigQuery upload failed ({type(exc).__name__}: {exc}). "
            f"Rows written to {fallback} so the run can be loaded later.",
            file=sys.stderr,
        )
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
