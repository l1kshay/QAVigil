"""QAVigil test-run analytics dashboard.

Answers three questions about suite health over time:
  1. Is the pass rate trending up or down?
  2. Which tests flake most often?
  3. Is the suite getting slower?

Run it:
    pip install -r analytics/requirements.txt
    streamlit run analytics/dashboard_app.py

Data source: BigQuery when configured, otherwise a local JSONL produced by
``export_to_bigquery.py --dry-run``. The local path exists so the dashboard can
be developed, demonstrated and reviewed without cloud credentials at all.

Security: this app reads with a **read-only** service account, separate from the
write-scoped one the export step uses. See ARCHITECTURE.md section 6.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSONL = PROJECT_ROOT / "reports" / "test_runs.jsonl"

# --- design tokens ----------------------------------------------------------
# Validated with the data-viz palette validator: all six checks pass in both
# light and dark modes (worst adjacent CVD dE 24.7 light / 26.8 dark).
# Status colours are reserved and always ship with a text label, never colour
# alone, so meaning never depends on hue.
PALETTE = {
    "light": {
        "surface": "#fcfcfb",
        "text_primary": "#0b0b0b",
        "text_secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series_1": "#2a78d6",   # blue - ui
        "series_2": "#eb6834",   # orange - api
        "good": "#0ca30c",
        "warning": "#fab219",
        "critical": "#d03b3b",
    },
    "dark": {
        "surface": "#1a1a19",
        "text_primary": "#ffffff",
        "text_secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series_1": "#3987e5",
        "series_2": "#d95926",
        "good": "#0ca30c",
        "warning": "#fab219",
        "critical": "#d03b3b",
    },
}

STATUS_ORDER = ["passed", "flaky", "failed", "skipped"]


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
#: Streamlit secrets key holding the READ-ONLY service account, as a TOML table
#: whose keys mirror the downloaded JSON key's fields.
SERVICE_ACCOUNT_SECRET = "gcp_service_account"


def service_account_info() -> dict | None:
    """The reader service account from Streamlit secrets, or None if absent.

    Absence is a normal, supported state - it is what every local JSONL-only
    run looks like - so it must never raise. ``st.secrets`` itself throws when
    no secrets file exists at all, rather than returning empty, which is why
    the lookup is wrapped.
    """
    try:
        if SERVICE_ACCOUNT_SECRET in st.secrets:
            return dict(st.secrets[SERVICE_ACCOUNT_SECRET])
    except Exception:
        # No secrets.toml, or it is unreadable. Either way: no service account.
        return None
    return None


def build_bigquery_client(project: str):
    """A BigQuery client, authenticated however this host allows.

    Streamlit Community Cloud has no Application Default Credentials, so a
    deployed dashboard must carry its own key - supplied as a Streamlit secret
    rather than a file, since there is nowhere to put a file. Everywhere else
    (a laptop with ``gcloud auth``, or a GCP host) ADC is present and no secret
    is needed, so the secret is preferred when set and ADC is the fallback.

    Read-only access is enforced by the credential's IAM role
    (``bigquery.dataViewer``), not by this code - see analytics/README.md.
    """
    from google.cloud import bigquery  # noqa: PLC0415

    info = service_account_info()
    if info is None:
        return bigquery.Client(project=project), "application default credentials"

    from google.oauth2 import service_account  # noqa: PLC0415 - ships with the BQ client

    credentials = service_account.Credentials.from_service_account_info(info)
    return (
        bigquery.Client(credentials=credentials, project=project or credentials.project_id),
        "service account from Streamlit secrets",
    )


@st.cache_data(ttl=300)
def load_from_bigquery(project: str, dataset: str, table: str) -> tuple[pd.DataFrame, str]:
    """Read run history from BigQuery. Imported lazily so the JSONL path needs no SDK."""
    client, auth_method = build_bigquery_client(project)
    query = f"""
        SELECT run_id, test_name, suite, status, duration_seconds,
               run_timestamp, branch, commit_sha, retry_count, marker
        FROM `{project}.{dataset}.{table}`
        ORDER BY run_timestamp
    """
    return client.query(query).to_dataframe(), auth_method


@st.cache_data(ttl=60)
def load_from_jsonl(path_str: str) -> pd.DataFrame:
    """Read run history from newline-delimited JSON."""
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    with path.open(encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return pd.DataFrame(rows)


# Exception class names that mean "the credential was missing, rejected, or
# insufficient". Matched by name so this module never has to import google.auth
# just to classify an error.
_AUTH_ERROR_NAMES = frozenset({
    "DefaultCredentialsError",
    "RefreshError",
    "TransportError",
    "Forbidden",
    "Unauthorized",
    "PermissionDenied",
    "Unauthenticated",
})


def explain_bigquery_failure(exc: Exception) -> str:
    """Say what actually went wrong, rather than blaming the credential.

    The first version of this warning named the attempted credential for
    *every* failure. That is actively misleading, and it cost real time: a
    missing ``db-dtypes`` package surfaced as "could not read BigQuery using
    service account from Streamlit secrets", sending the reader to re-check a
    key that was working perfectly. Each cause gets its own sentence, and only
    the auth case mentions credentials.
    """
    name = type(exc).__name__
    text = str(exc)

    # google-cloud-bigquery raises a bare ValueError from to_dataframe() when
    # an optional extra is missing. It reads like a runtime fault but is a
    # packaging one, and it is emphatically not an auth problem.
    if isinstance(exc, ModuleNotFoundError) or "Please install" in text:
        return (
            f"A required Python package is missing ({name}: {text}). "
            "This is a dependency problem, not a credential one - install "
            "`analytics/requirements.txt` in the deployment environment."
        )

    if name in _AUTH_ERROR_NAMES or " 401 " in text or " 403 " in text:
        attempted = (
            f"the service account in the `{SERVICE_ACCOUNT_SECRET}` Streamlit secret"
            if service_account_info() is not None
            else (
                "application default credentials - no "
                f"`{SERVICE_ACCOUNT_SECRET}` secret is set, and this host may not have any"
            )
        )
        return (
            f"BigQuery rejected the credential ({name}: {text}). "
            f"It tried {attempted}. Check the key is the read-only one and that "
            "it has `bigquery.dataViewer` on this dataset plus `bigquery.jobUser`."
        )

    if name == "NotFound":
        return (
            f"BigQuery could not find the table ({name}: {text}). "
            "Check BQ_PROJECT, BQ_DATASET and BQ_TABLE - the credential "
            "authenticated, so this is a configuration problem, not an auth one."
        )

    return f"Could not read BigQuery ({name}: {text})."


def load_data() -> tuple[pd.DataFrame, str]:
    """Load history from whichever source is configured, and say which."""
    project = os.getenv("BQ_PROJECT")
    dataset = os.getenv("BQ_DATASET")
    table = os.getenv("BQ_TABLE", "test_runs")

    if project and dataset:
        try:
            frame, auth_method = load_from_bigquery(project, dataset, table)
            return frame, f"BigQuery ({dataset}.{table}, via {auth_method})"
        except Exception as exc:
            st.warning(
                f"{explain_bigquery_failure(exc)} Falling back to the local export."
            )

    return load_from_jsonl(str(DEFAULT_JSONL)), f"local file ({DEFAULT_JSONL.name})"


def prepare(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize types and derive the per-run ordering the charts need."""
    frame = frame.copy()
    frame["run_timestamp"] = pd.to_datetime(frame["run_timestamp"], utc=True, format="mixed")
    frame["duration_seconds"] = pd.to_numeric(frame["duration_seconds"], errors="coerce")
    frame["retry_count"] = pd.to_numeric(
        frame.get("retry_count", 0), errors="coerce"
    ).fillna(0).astype(int)
    return frame.sort_values("run_timestamp")


# ---------------------------------------------------------------------------
# aggregations
# ---------------------------------------------------------------------------
def per_run_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """One row per CI run: pass rate, counts, and wall-clock duration."""
    grouped = frame.groupby("run_id", sort=False)
    summary = grouped.agg(
        run_timestamp=("run_timestamp", "min"),
        tests=("test_name", "count"),
        duration_seconds=("duration_seconds", "sum"),
        branch=("branch", "first"),
    ).reset_index()

    counts = (
        frame.pivot_table(
            index="run_id", columns="status", values="test_name", aggfunc="count", fill_value=0
        )
        .reindex(columns=STATUS_ORDER, fill_value=0)
        .reset_index()
    )
    summary = summary.merge(counts, on="run_id", how="left")

    # A flaky test passed in the end, so it counts as a pass. Treating it as a
    # failure would make the pass-rate line swing on infrastructure noise and
    # train people to ignore it; flakiness gets its own chart instead.
    summary["pass_rate"] = (
        (summary["passed"] + summary["flaky"])
        / summary[STATUS_ORDER].sum(axis=1).replace(0, pd.NA)
        * 100
    ).round(1)

    return summary.sort_values("run_timestamp")


def flaky_leaderboard(frame: pd.DataFrame, limit: int = 10) -> pd.DataFrame:
    """Tests that flaked most often, worst first."""
    flaky = frame[frame["status"] == "flaky"]
    if flaky.empty:
        return pd.DataFrame(columns=["test_name", "occurrences", "short_name"])

    board = (
        flaky.groupby("test_name")
        .agg(occurrences=("run_id", "nunique"), retries=("retry_count", "sum"))
        .reset_index()
        .sort_values("occurrences", ascending=False)
        .head(limit)
    )
    # Full node ids are far too long for an axis; keep the test function name.
    board["short_name"] = board["test_name"].str.split("#").str[-1]
    return board


def duration_by_suite(frame: pd.DataFrame) -> pd.DataFrame:
    """Total wall-clock seconds per suite, per run."""
    return (
        frame.groupby(["run_id", "suite"])
        .agg(
            duration_seconds=("duration_seconds", "sum"),
            run_timestamp=("run_timestamp", "min"),
        )
        .reset_index()
        .sort_values("run_timestamp")
    )


# ---------------------------------------------------------------------------
# charts
# ---------------------------------------------------------------------------
def _base(colors: dict[str, str]) -> dict:
    """Shared Altair config: recessive grid and axes, ink in text tokens."""
    return {
        "background": colors["surface"],
        "axis": {
            "domainColor": colors["axis"],
            "gridColor": colors["grid"],
            "gridWidth": 1,
            "labelColor": colors["muted"],
            "tickColor": colors["axis"],
            "titleColor": colors["text_secondary"],
            "labelFontSize": 11,
            "titleFontSize": 12,
            "titleFontWeight": "normal",
        },
        "legend": {
            "labelColor": colors["text_secondary"],
            "titleColor": colors["text_secondary"],
            "labelFontSize": 12,
        },
        "view": {"stroke": "transparent"},
    }


def pass_rate_chart(summary: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Pass rate over time. One series, so no legend - the title names it."""
    hover = alt.selection_point(
        fields=["run_timestamp"], nearest=True, on="pointerover", empty=False
    )

    line = (
        alt.Chart(summary)
        .mark_line(color=colors["series_1"], strokeWidth=2, point=False)
        .encode(
            x=alt.X("run_timestamp:T", title="Run"),
            # Not zero-based on purpose: a suite that lives between 95 and 100%
            # shows nothing useful on a 0-100 axis. The axis is labelled, and a
            # line chart of a rate is not a magnitude comparison.
            y=alt.Y(
                "pass_rate:Q",
                title="Pass rate (%)",
                scale=alt.Scale(zero=False, domainMax=100, nice=True),
            ),
        )
    )

    points = (
        alt.Chart(summary)
        .mark_point(
            color=colors["series_1"], size=80, filled=True,
            stroke=colors["surface"], strokeWidth=2,
        )
        .encode(
            x="run_timestamp:T",
            y="pass_rate:Q",
            opacity=alt.condition(hover, alt.value(1), alt.value(0)),
            tooltip=[
                alt.Tooltip("run_timestamp:T", title="Run at"),
                alt.Tooltip("pass_rate:Q", title="Pass rate (%)"),
                alt.Tooltip("tests:Q", title="Tests"),
                alt.Tooltip("passed:Q", title="Passed"),
                alt.Tooltip("flaky:Q", title="Flaky"),
                alt.Tooltip("failed:Q", title="Failed"),
            ],
        )
        .add_params(hover)
    )

    return (line + points).properties(height=260).configure(**_base(colors))


def flaky_chart(board: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Flaky frequency. Horizontal bars: long test names need horizontal room."""
    return (
        alt.Chart(board)
        .mark_bar(
            color=colors["warning"],
            cornerRadiusTopRight=4, cornerRadiusBottomRight=4,
            height=18,
        )
        .encode(
            x=alt.X("occurrences:Q", title="Runs in which it flaked"),
            y=alt.Y("short_name:N", title=None, sort="-x"),
            tooltip=[
                alt.Tooltip("test_name:N", title="Test"),
                alt.Tooltip("occurrences:Q", title="Runs flaked"),
                alt.Tooltip("retries:Q", title="Total retries"),
            ],
        )
        .properties(height=max(len(board) * 28, 80))
        .configure(**_base(colors))
    )


def duration_chart(durations: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Suite duration over time. Two series, so a legend is always present."""
    return (
        alt.Chart(durations)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=45, filled=True))
        .encode(
            x=alt.X("run_timestamp:T", title="Run"),
            y=alt.Y("duration_seconds:Q", title="Duration (seconds)"),
            color=alt.Color(
                "suite:N",
                title="Suite",
                scale=alt.Scale(
                    domain=["ui", "api", "environment"],
                    range=[colors["series_1"], colors["series_2"], colors["muted"]],
                ),
            ),
            tooltip=[
                alt.Tooltip("run_timestamp:T", title="Run at"),
                alt.Tooltip("suite:N", title="Suite"),
                alt.Tooltip("duration_seconds:Q", title="Seconds", format=".1f"),
            ],
        )
        .properties(height=260)
        .configure(**_base(colors))
    )


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="QAVigil - suite health", layout="wide")

    st.title("QAVigil suite health")
    st.caption(
        "Pass rate, flakiness and duration across test runs of "
        "automationexercise.com."
    )

    with st.sidebar:
        st.header("View")
        theme = st.radio("Theme", ["light", "dark"], horizontal=True)
    colors = PALETTE[theme]

    raw, source = load_data()
    if raw.empty:
        st.info(
            "No run history yet.\n\n"
            "Generate some locally with:\n\n"
            "```\npytest\npython analytics/export_to_bigquery.py --dry-run\n```\n\n"
            "or set `BQ_PROJECT` and `BQ_DATASET` to read from BigQuery."
        )
        return

    frame = prepare(raw)

    with st.sidebar:
        suites = sorted(frame["suite"].dropna().unique())
        chosen = st.multiselect("Suites", suites, default=suites)
        if chosen:
            frame = frame[frame["suite"].isin(chosen)]
        st.caption(f"Source: {source}")

    summary = per_run_summary(frame)
    latest = summary.iloc[-1]
    previous = summary.iloc[-2] if len(summary) > 1 else None

    # Headline numbers first. These are single values, and a single value is a
    # stat tile, not a chart.
    col1, col2, col3, col4 = st.columns(4)
    col1.metric(
        "Pass rate (latest run)",
        f"{latest['pass_rate']:.1f}%",
        delta=(
            f"{latest['pass_rate'] - previous['pass_rate']:+.1f} pts"
            if previous is not None else None
        ),
    )
    col2.metric("Tests", int(latest["tests"]))
    col3.metric(
        "Flaky (latest run)",
        int(latest["flaky"]),
        delta=(
            int(latest["flaky"] - previous["flaky"]) if previous is not None else None
        ),
        delta_color="inverse",
    )
    col4.metric("Duration (latest run)", f"{latest['duration_seconds']:.0f}s")

    st.subheader("Pass rate over time")
    st.altair_chart(pass_rate_chart(summary, colors), use_container_width=True)

    left, right = st.columns(2)

    with left:
        st.subheader("Most frequently flaky tests")
        board = flaky_leaderboard(frame)
        if board.empty:
            st.success("No flaky tests recorded. Every failure so far was reproducible.")
        else:
            st.altair_chart(flaky_chart(board, colors), use_container_width=True)

    with right:
        st.subheader("Suite duration over time")
        st.altair_chart(duration_chart(duration_by_suite(frame), colors), use_container_width=True)

    # A table view is the accessibility fallback for every chart above, and the
    # thing anyone will want when a chart raises a question it cannot answer.
    with st.expander("Run history (table view)"):
        st.dataframe(
            summary[
                ["run_timestamp", "run_id", "branch", "tests", *STATUS_ORDER,
                 "pass_rate", "duration_seconds"]
            ],
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
