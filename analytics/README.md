# QAVigil analytics (Phase 7)

Turns test-run history into a picture of suite health over time: is the pass
rate trending down, which tests flake most, and is the suite getting slower.

**This layer is optional and entirely separate from the test suite.** Nothing in
`tests/`, `pages/` or `api_clients/` imports anything here, and the BigQuery and
Streamlit dependencies live in `analytics/requirements.txt` rather than the
project's `requirements.txt` — cloning this repo to run tests must never require
a cloud SDK.

```
Allure results  ->  export_to_bigquery.py  ->  BigQuery test_runs table
                                                  |
                                    +-------------+-------------+
                                    v                           v
                            Looker Studio               dashboard_app.py
                            (hosted by Google)          (Streamlit Cloud)
```

---

## Try it with no cloud account at all

The exporter and the dashboard both work against a local file, so you can see
the whole thing working before deciding whether to set up BigQuery:

```bash
pytest                                              # produce some results
python analytics/export_to_bigquery.py --dry-run    # -> reports/test_runs.jsonl

pip install -r analytics/requirements.txt
streamlit run analytics/dashboard_app.py            # reads the JSONL
```

A single run makes for a dull trend line — the charts get interesting after a
few runs have accumulated.

---

## What gets recorded

One row per test per run, in an append-only table. Full field descriptions are
in [`bq_schema.json`](bq_schema.json).

| Field | Notes |
|---|---|
| `run_id` | GitHub Actions run id, or a local uuid |
| `test_name` | full pytest node id |
| `suite` | `ui`, `api`, or `environment` |
| `status` | `passed`, `failed`, `flaky`, `skipped` |
| `duration_seconds` | summed across retries |
| `run_timestamp` | UTC; the partitioning column |
| `branch`, `commit_sha` | what was under test |
| `retry_count`, `marker` | attempts beyond the first; `smoke`/`regression` |

### How `flaky` is determined

`pytest-rerunfailures` reruns a failing test once in CI, and Allure writes one
result file per attempt. Attempts share a `historyId`, so
`collapse_retries()` groups by it: if any attempt failed and the final one
passed, the row is recorded as `flaky`.

This matters more than it sounds. Uploaded raw, one flaky test would appear as
*both* a failure and a pass, quietly corrupting every pass-rate figure the
dashboards show.

The dashboard then counts a flaky test as a **pass** in the pass-rate line — it
did pass in the end — and gives flakiness its own chart. Folding flakes into the
failure line would make the headline metric swing on infrastructure noise, which
is how a dashboard trains people to ignore it.

---

## One-time BigQuery setup

These steps need a Google Cloud account and cannot be automated from this
repository.

**1. Create the dataset and table**

```bash
gcloud config set project YOUR_PROJECT_ID
bq mk --location=US --dataset YOUR_PROJECT_ID:qavigil

bq mk --table \
  --time_partitioning_field run_timestamp \
  --time_partitioning_type DAY \
  YOUR_PROJECT_ID:qavigil.test_runs \
  analytics/bq_schema.json
```

Partitioning on `run_timestamp` keeps the dashboards' date-range queries cheap
as history accumulates.

**2. Create two service accounts, not one**

The writer and the reader are deliberately separate. The export step runs on
every CI job and its key sits in repository secrets; the dashboard is a
deployed web app. Neither should be able to do the other's job.

```bash
# Writer - used by CI. Append-only in practice, scoped to this dataset.
gcloud iam service-accounts create qavigil-exporter
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:qavigil-exporter@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor" \
  --condition="expression=resource.name.startsWith('projects/YOUR_PROJECT_ID/datasets/qavigil'),title=qavigil-dataset-only"

# Reader - used by the dashboard. Cannot write.
gcloud iam service-accounts create qavigil-dashboard
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:qavigil-dashboard@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" \
  --condition="expression=resource.name.startsWith('projects/YOUR_PROJECT_ID/datasets/qavigil'),title=qavigil-dataset-only"
```

Both also need `roles/bigquery.jobUser` at project level to run queries.

**3. Add the repository secrets**

Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `BQ_PROJECT` | your GCP project id |
| `BQ_DATASET` | `qavigil` |
| `BQ_TABLE` | `test_runs` |
| `BQ_CREDENTIALS_JSON` | the **writer** key's full JSON |

The CI export step skips itself entirely when `BQ_PROJECT` is unset, so forks
and unconfigured clones are unaffected.

---

## Dashboards

The plan calls for **one or two dashboards done well**, not three shallow ones.

### Looker Studio (recommended primary)

Free, and connects to BigQuery natively with no intermediate service.

1. [lookerstudio.google.com](https://lookerstudio.google.com) → Create → Data source → BigQuery
2. Select `YOUR_PROJECT.qavigil.test_runs`
3. Build three charts against these fields:

| Chart | Type | Dimension | Metric |
|---|---|---|---|
| Pass rate over time | time series | `run_timestamp` (day) | `COUNTIF(status IN ('passed','flaky')) / COUNT(1)` |
| Flaky leaderboard | horizontal bar | `test_name` | `COUNTIF(status = 'flaky')`, sorted desc |
| Suite duration | time series | `run_timestamp` (day), breakdown `suite` | `SUM(duration_seconds)` |

Share with "anyone with the link can view" for a portfolio-visible artifact.

### Streamlit (`dashboard_app.py`)

The code-owned interactive view — the same three questions, in a repository you
control rather than a hosted BI tool's UI.

Deploy to [share.streamlit.io](https://share.streamlit.io): point it at this
repo, set the main file to `analytics/dashboard_app.py`, and add the **reader**
credentials under the app's Secrets. This is deliberately separate from the
GitHub Pages test report — one hosts the per-run report, the other the
across-run trend.

Its colours were validated for colour-vision deficiency and contrast in both
light and dark modes; status meaning is always carried by a text label, never
by hue alone.

---

## What still needs a human

Everything below requires accounts and web UIs, and cannot be done from here:

- [ ] Create the GCP project, dataset, and table (step 1)
- [ ] Create the two service accounts and download the writer key (step 2)
- [ ] Add the four repository secrets (step 3)
- [ ] Build the Looker Studio report and set its sharing
- [ ] Deploy the Streamlit app and add the reader credentials to its Secrets
- [ ] Enable GitHub Pages (Settings → Pages → Source: GitHub Actions) — needed
      for the Phase 6 test report, not for analytics
