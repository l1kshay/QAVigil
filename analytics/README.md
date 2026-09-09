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
| `BQ_CREDENTIALS_JSON` | the **writer** key's full JSON, pasted raw — not base64, not a path |

`BQ_TABLE` is optional; the exporter defaults to `test_runs`. The workflow
writes `BQ_CREDENTIALS_JSON` to a temp file and points
`GOOGLE_APPLICATION_CREDENTIALS` at it for the life of that step — so
`GOOGLE_APPLICATION_CREDENTIALS` is *not* itself a secret you create.

The CI export step skips itself entirely when `BQ_PROJECT` is unset, so forks
and unconfigured clones are unaffected.

The dashboard's **reader** key is not a GitHub secret at all — it lives in
Streamlit Cloud's own Secrets panel, in a different format. See
[Streamlit secrets](#streamlit-secrets) below.

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
repo and set the main file to `analytics/dashboard_app.py`. This is deliberately
separate from the GitHub Pages test report — one hosts the per-run report, the
other the across-run trend.

#### Streamlit secrets

Streamlit Community Cloud has **no Application Default Credentials**, so a
deployed dashboard cannot authenticate the way a laptop with `gcloud auth` does
— it has to carry its own key, and there is nowhere to put a key *file*. So the
reader credential is supplied as a Streamlit secret and loaded by
`build_bigquery_client()` via
`service_account.Credentials.from_service_account_info()`.

Paste this into the app's **Settings → Secrets** panel (never into the repo):

```toml
# Top-level strings. Streamlit promotes str/int/float top-level secrets into
# os.environ, which is how the app's os.getenv() calls see them.
BQ_PROJECT = "your-gcp-project-id"
BQ_DATASET = "qavigil"
BQ_TABLE   = "test_runs"          # optional; defaults to test_runs

# The READER key, as a TOML table. Each key mirrors a field of the downloaded
# service-account JSON. Nested tables are NOT promoted to os.environ, which is
# why this one is read through st.secrets rather than os.getenv.
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

Use the **reader** key here (`bigquery.dataViewer`), never the writer key that
sits in GitHub Actions secrets. Read-only is enforced by that IAM role, not by
the app's code.

The `[gcp_service_account]` table is optional. When it is absent the app falls
back to Application Default Credentials, and when BigQuery is not configured at
all it reads the local JSONL — so `streamlit run` works on a laptop with no
secrets file of any kind. The sidebar names which source and which credential
were actually used, and a failed BigQuery read says which credential it tried.

#### Python version

`runtime.txt` at the repo root pins `python-3.12`, matching CI and local
development. Note that Streamlit Community Cloud's authoritative setting is the
**Python version selector in the deploy dialog's Advanced settings** — set it to
3.12 there. `runtime.txt` records the intended version and is honoured by hosts
that read the convention (Render, Heroku); do not rely on it alone for
Streamlit Cloud.

#### Design notes

Its colours were validated for colour-vision deficiency and contrast in both
light and dark modes; status meaning is always carried by a text label, never
by hue alone.

---

## What still needs a human

Everything below requires accounts and web UIs, and cannot be done from here:

- [ ] Create the GCP project, dataset, and table (step 1)
- [ ] Create the two service accounts and download both keys (step 2)
- [ ] Add the repository secrets (step 3) — three are required
      (`BQ_PROJECT`, `BQ_DATASET`, `BQ_CREDENTIALS_JSON`); `BQ_TABLE` is only
      needed if the table is not named `test_runs`
- [ ] Build the Looker Studio report and set its sharing
- [ ] Deploy the Streamlit app: set the Python version to 3.12 in Advanced
      settings, and add the reader key as `[gcp_service_account]` in its Secrets
- [ ] Enable GitHub Pages (Settings → Pages → Source: GitHub Actions) — needed
      for the Phase 6 test report, not for analytics
