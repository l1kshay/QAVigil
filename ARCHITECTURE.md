# QAVigil: Automated UI + API Testing Suite (with Optional Test Analytics Layer)
## Architecture & Project Plan — v2

---

## 1. Project Overview

**Summary:** QAVigil is a CI-integrated test automation system that validates both the user interface and API layer of a target application — **automationexercise.com**, a public demo e-commerce site with a documented REST API — using a maintainable Page Object Model for UI tests and a structured, data-driven approach for API tests. Every push to the repository triggers the full suite automatically, producing a consolidated, human-readable test report that distinguishes genuine regressions from flaky failures. An **optional analytics layer** turns raw test run history into a resume-worthy BI dashboard, mirroring how a real QA org tracks suite health over time.

**Target Users:**
- QA/SDET teams needing a reusable, maintainable automation framework for a web application
- Development teams wanting regression confidence on every code change via CI
- Secondary audience: technical evaluators (recruiters/interviewers) assessing test design discipline, framework architecture, and data/BI versatility — not just script-writing ability

**Core Features:**
- UI test suite covering core user flows (login, search/browse, cart, checkout)
- API test suite covering CRUD-equivalent operations, auth, and negative/edge cases
- Page Object Model (POM) layer separating test logic from UI locators
- Data-driven test execution using externalized test data
- CI pipeline that runs the full suite automatically on every push
- Consolidated Allure/HTML test report with pass/fail/flaky classification
- Environment-configurable test targets (e.g., staging vs. local)
- **(Optional)** A test-run analytics layer: historical pass/fail/flaky/duration metrics exported to BigQuery and visualized in a BI tool, deployed as a shareable dashboard

---

## 2. Recommended Tech Stack & Tools

**Frontend (Under Test — not built by this project)**
- **automationexercise.com** — public demo e-commerce app with both a real UI (login, products, cart, checkout) and a documented REST API (`/api/productsList`, `/api/brandsList`, `/api/searchProduct`, `/api/verifyLogin`, `/api/createAccount`, `/api/getUserDetailByEmail`). Using one app for both layers is more realistic than testing two unrelated demo sites.

**Backend/Test Execution Layer**
- **Python** — single language across UI, API, and analytics tooling
- **Playwright** (primary UI automation) — auto-waiting reduces flaky failures, multi-browser support, most-growing tool in QA job postings; **Selenium** noted as an optional secondary implementation for tooling-range awareness
- **Requests** (API testing) — explicit, lightweight HTTP calls, easy to explain in an interview

**Test Framework**
- **Pytest** — fixtures, parametrization, markers (`smoke` / `regression`)

**Database**
- Not required as a core component — test data is external (CSV/JSON/YAML), not an application database. **BigQuery is used only for the optional analytics layer** (test run history), never as an application datastore, to keep this project scoped to testing.

**Authentication**
- Test-level authentication only (login flow as a tested feature, API session/token handling in test setup) — no auth system is built.

**Additional Libraries / Services**
- **Allure** (preferred) or pytest-html — human-readable, categorized test reports
- **Faker** — realistic test data, avoids hardcoded values
- **python-dotenv** — environment-specific config without hardcoding
- **pytest-xdist** — parallel test execution
- **jsonschema** — structural validation of API responses
- **PyYAML** — structured, readable test data/config

**Visualization / BI Tools — used conditionally, only where they add real value**
QAVigil is a testing framework first; these are **not** part of the core suite and should only be introduced for the optional analytics extension (Module 9 / Phase 7 below), not bolted on for their own sake:
- **Google BigQuery** — stores structured test-run history (one row per test execution: test name, suite, status, duration, run date, flaky flag)
- **Looker Studio** (free, connects natively to BigQuery) — primary dashboard: pass/fail trend over time, flaky-test leaderboard, suite duration trend
- **Tableau Public** — alternative/companion dashboard for portfolio breadth, published free, embeddable
- **Power BI** — alternative/companion dashboard (Power BI Desktop + published report) if Windows tooling access is available; otherwise Looker Studio + Tableau Public alone are sufficient for resume purposes
- **Rule of thumb Claude Code should follow:** build the BigQuery export pipeline once, then connect *at most one or two* of these BI tools well, rather than building three shallow, redundant dashboards. Depth over tool-count.

**Development & Deployment Tools**
- **Git / GitHub** — version control
- **GitHub Actions** — CI pipeline execution on every push/PR
- **VS Code** — development environment
- **GitHub Pages** — hosting the published Allure/HTML *test* report (existing plan, unchanged)
- **Separate deployment platform for the analytics dashboard app (if built):** since the BI dashboards themselves (Looker Studio/Tableau Public) are hosted by their own platforms, the *only* thing QAVigil needs to self-host is a lightweight Python app (e.g., a Streamlit summary dashboard reading from BigQuery) if we want an interactive, code-owned artifact beyond the BI tool's own hosting. That app is deployed on **Streamlit Community Cloud** (free, Python-native, distinct from GitHub Pages, and a strong resume line: "deployed Python data app"). Render or Fly.io are noted as alternatives if Streamlit's constraints don't fit.

---

## 3. System Architecture

**High-Level Architecture Description**
QAVigil follows a **layered test-automation architecture** separating four core concerns: a **Page Object Layer**, a **Test Logic Layer**, a **Test Data Layer**, and a **Reporting Layer**. A **CI Orchestration Layer** (GitHub Actions) triggers the suite and publishes results on every code change. An **optional Analytics Layer** sits downstream of Reporting, transforming run history into a BI-consumable dataset.

**Architecture Diagram Description (Text)**
```
[Target Application Under Test: automationexercise.com]
   ├── Web UI  ◄────────────┐
   └── REST API ◄───────┐   │
                         │   │
              [API Client Layer]   [Page Object Layer]
              (requests wrappers)   (locators + actions per page)
                         │              │
                         └──────┬───────┘
                                ▼
                     [Test Logic Layer]
                (pytest test cases: ui/, api/)
                                │
                                ▼
                     [Test Data Layer]
                (YAML/JSON fixtures, Faker-generated data)
                                │
                                ▼
                     [Test Execution — pytest + pytest-xdist]
                                │
                                ▼
                     [Reporting Layer — Allure/HTML]
                                │
                    ┌───────────┴────────────┐
                    ▼                         ▼
        [Published Report —          [OPTIONAL: Analytics Export
         GitHub Pages]                — run results → BigQuery]
                                                │
                                                ▼
                                    [BI Layer — Looker Studio /
                                     Tableau Public / Power BI]
                                                │
                                                ▼
                                    [OPTIONAL: Streamlit summary
                                     app on Streamlit Community Cloud]

[GitHub Actions] → triggers execution on every push/PR, publishes report
                    as artifact, and (optionally) appends run results to BigQuery
```

**Component Breakdown**
- **Page Object Component** — one class per app page/screen, exposing intent-named actions
- **API Client Component** — thin wrapper functions per endpoint/resource
- **Test Logic Component** — assertions and scenarios, split into `tests/ui/` and `tests/api/`
- **Test Data Component** — externalized fixtures decoupled from test code
- **Configuration Component** — environment-specific settings via `.env`
- **Execution Component** — pytest runner with smoke/regression markers
- **Reporting Component** — Allure/HTML generation and classification of results
- **CI Component** — GitHub Actions workflow definitions
- **(Optional) Analytics Export Component** — parses Allure/pytest JSON results after each run and appends a normalized record to BigQuery
- **(Optional) BI Dashboard Component** — Looker Studio/Tableau Public report reading from BigQuery; optionally a small Streamlit app for a code-owned interactive view

**Data Flow Overview**
1. A developer pushes code (or the schedule triggers a run); GitHub Actions provisions the environment and installs dependencies
2. Pytest collects tests from `tests/ui/` and `tests/api/` based on marker (`smoke` for fast feedback, `regression` for full coverage)
3. UI tests interact with automationexercise.com exclusively through Page Object methods; API tests interact exclusively through the API Client layer
4. Both layers pull input values from the Test Data layer rather than embedding literals
5. Test results (pass/fail/skip, with screenshots/traces on UI failure) are collected by the reporting plugin
6. Allure/HTML report is generated and published as a CI artifact and to GitHub Pages
7. **(Optional)** A post-run step parses the results JSON and appends a row (test name, suite, status, duration, timestamp, flaky flag) to a BigQuery table
8. **(Optional)** Looker Studio/Tableau Public dashboards refresh from BigQuery; the optional Streamlit app queries BigQuery directly and is deployed on Streamlit Community Cloud
9. On failure, the CI job fails the build/PR check, same signal a real product team would rely on before merging

**Folder / Project Structure Recommendation**
```
qavigil/
├── pages/
│   ├── base_page.py
│   ├── login_page.py
│   ├── search_page.py
│   ├── cart_page.py
│   └── checkout_page.py
├── api_clients/
│   ├── base_client.py
│   ├── auth_client.py
│   └── product_client.py
├── tests/
│   ├── ui/
│   │   ├── test_login.py
│   │   ├── test_search.py
│   │   └── test_checkout.py
│   └── api/
│       ├── test_auth.py
│       ├── test_products_crud.py
│       └── test_negative_cases.py
├── test_data/
│   ├── users.yaml
│   └── products.json
├── config/
│   └── settings.py
├── reports/
├── analytics/                     # OPTIONAL — only if BI layer is built
│   ├── export_to_bigquery.py
│   ├── bq_schema.json
│   └── dashboard_app.py           # optional Streamlit app
├── conftest.py
├── pytest.ini
├── .github/
│   └── workflows/
├── .env.example
├── requirements.txt
├── CLAUDE.md
└── README.md
```

---

## 4. Database Design

No application database — this project tests an external target application. The "data design" is the **test data structure** (unchanged from v1), plus an **optional analytics schema**:

| Data File | Key Fields | Purpose |
|---|---|---|
| `users.yaml` | `username`, `password`, `role`, `expected_result` | Valid and invalid credential sets for login/auth test cases |
| `products.json` | `product_id`, `name`, `price`, `expected_status` | Product fixtures for API and UI search/cart tests |
| `edge_cases.yaml` | `input_field`, `input_value`, `expected_behavior` | Boundary and negative-case inputs |

**Optional BigQuery table — `test_runs`:**

| Field | Type | Purpose |
|---|---|---|
| `run_id` | STRING | Unique CI run identifier |
| `test_name` | STRING | Full pytest node ID |
| `suite` | STRING | `ui` or `api` |
| `status` | STRING | `passed` / `failed` / `flaky` / `skipped` |
| `duration_seconds` | FLOAT | Test execution time |
| `run_timestamp` | TIMESTAMP | When the run occurred |
| `branch` | STRING | Git branch that triggered the run |

**Relationships:** None relational — independent fixture files for test data; a single flat, append-only table for analytics.

**Constraints/Conventions:**
- Every test data file must define an explicit `expected_result`/`expected_status` field
- No production or real user data ever used
- BigQuery table is append-only and write-scoped to a single service account with minimal permissions

---

## 5. Module / Feature Breakdown

**Modules 1–8** are unchanged from v1 (Page Object Layer, API Client Layer, UI Test Suite, API Test Suite, Test Data Management, Reporting, CI Orchestration, Configuration Management).

**Module 9 — Test Analytics & BI Dashboard (Optional, build last)**
- Purpose: Turn raw test run history into a visual, resume-relevant artifact demonstrating BI/data tooling alongside automation skill
- Key functionality: post-run export script parses Allure/pytest results → normalizes → appends to a BigQuery table; a Looker Studio (and optionally Tableau Public) dashboard visualizes pass-rate trend, flaky-test frequency, and suite duration over time; an optional small Streamlit app provides a code-owned interactive view of the same data
- Tools: BigQuery, Looker Studio, Tableau Public and/or Power BI (pick one or two, not all three shallowly), Streamlit (optional), Streamlit Community Cloud (deployment)
- **Explicitly optional and last in sequence** — the core testing framework must be complete and solid on its own before this is attempted; do not let this module dilute the primary QA-engineering deliverable

---

## 6. Security & Best Practices

Unchanged from v1, plus:
- BigQuery service account credentials (JSON key) are never committed — loaded via GitHub Actions Secrets and `.env` locally, same as all other credentials
- The BigQuery service account is scoped to only `bigquery.dataEditor` on the single `test_runs` table/dataset — no project-wide access
- If a Streamlit app is deployed, it reads BigQuery with a **read-only** service account, separate from the write-scoped one used by the export step

(All original v1 rules remain: strict POM discipline, no `sleep()`, test independence, one assertion focus per test, consistent markers, meaningful commits, README with a "known flaky tests" section.)

---

## 7. Development Roadmap (High-Level)

**Phase 1 — Framework Skeleton**
Set up project structure, confirm automationexercise.com and its API endpoints are reachable, establish Page Object and API client base classes, configure pytest with basic fixtures.

**Phase 2 — UI Test Suite**
Build Page Objects and UI test cases (login → search → cart → checkout), happy path first.

**Phase 3 — API Test Suite**
Build the API client layer and CRUD/auth/negative-case tests with schema validation.

**Phase 4 — Test Data Externalization**
Move all hardcoded inputs into YAML/JSON fixtures; integrate Faker for dynamic data.

**Phase 5 — Reporting**
Integrate Allure, configure failure screenshots/traces, validate report readability.

**Phase 6 — CI Integration & Documentation**
Configure GitHub Actions (smoke on push, regression on schedule/PR), publish report to GitHub Pages, finalize README and `CLAUDE.md`.

**Phase 7 — Optional Analytics & BI Layer (only after Phases 1–6 are solid)**
Build the BigQuery export step into the CI workflow, connect Looker Studio (and optionally Tableau Public or Power BI) to visualize run history, and — if desired — build and deploy a small Streamlit summary app to Streamlit Community Cloud.

---

## 8. Tools Summary Table

| Category | Tool/Technology | Purpose |
|---|---|---|
| UI Automation | Playwright (primary) / Selenium (optional secondary) | Browser automation with auto-waiting |
| API Testing | Requests | Building and validating HTTP calls |
| Test Framework | Pytest | Execution, fixtures, parametrization, markers |
| Test Data | PyYAML, Faker | Externalized, realistic test inputs |
| Response Validation | jsonschema | Structural validation of API responses |
| Reporting | Allure / pytest-html | Categorized, shareable test reports |
| Parallel Execution | pytest-xdist | Faster CI runs |
| Secrets Management | python-dotenv | Environment-specific config without hardcoding |
| Version Control | Git / GitHub | Source control and collaboration |
| CI/CD | GitHub Actions | Automated suite execution and report publishing |
| Report Hosting | GitHub Pages | Hosting the published Allure/HTML test report |
| **Analytics Store (optional)** | **Google BigQuery** | Structured storage of historical test-run results |
| **BI Visualization (optional)** | **Looker Studio, Tableau Public, Power BI** | Trend/flakiness/duration dashboards (pick 1–2, not all) |
| **Analytics App Deployment (optional)** | **Streamlit + Streamlit Community Cloud** | Hosting a code-owned interactive dashboard, separate from GitHub Pages |
| Development Environment | VS Code | Primary coding environment |

---

## 9. Notes for Claude Code

- Use Power BI, Tableau, Looker Studio, and BigQuery **only** when building the optional Phase 7 analytics layer — never introduce them into the core UI/API testing framework.
- Before starting Phase 7, check for and use any relevant **Claude Code skills or plugins** already available in this environment (e.g., data-analysis, xlsx, or BI-related skills) rather than writing everything from scratch — but confirm with me before adding a new plugin/skill dependency to the project.
- If a genuinely better-fitting tool or skill becomes available mid-project, propose the change and reasoning before switching — don't silently substitute tools from this plan.

---

## 10. Implementation Decisions Log

Decisions taken while building Phases 1–6 that this plan did not settle in advance. Recorded here so the reasoning survives, rather than living only in commit messages.

### 10.1 The target API reports status in the response body, not the HTTP status

**Discovered:** Phase 1, verifying the API against `/api_list` before writing any tests.

automationexercise.com answers **every** request with `HTTP 200` and puts the real outcome in the JSON body's `responseCode` field. A missing parameter returns `HTTP 200` with `{"responseCode": 400, "message": "Bad request, ..."}`. Even an unsupported HTTP method returns `HTTP 200` with `responseCode: 405`.

This is load-bearing, not a curiosity. A suite asserting on `response.status_code` would see 200 everywhere, and **every negative test would pass without testing anything**.

**Decision:** `ApiResponse.status` resolves to the body's `responseCode`; `http_status` is kept separately for the rare assertion that cares about the transport layer. The assumption is asserted explicitly in `tests/api/test_negative_cases.py::test_errors_are_reported_in_the_body_not_the_http_status`, so if the site ever adopts real status codes, that test fails loudly rather than the negative suite silently going green.

### 10.2 Search matches product category, not only name

**Discovered:** Phase 2, via a legitimately failing test.

Searching `dress` returns items such as "Sleeves Top and Short - Blue & Pink" whose *name* lacks the word but whose *category* is Dress. An early UI test asserted every result name contained the term; it was encoding a false assumption about the feature.

**Decision:** the UI test now asserts a true property (searching a product's own name returns it). Category-level relevance is asserted in the API suite, where the `category` field actually exists — the UI's listing grid does not show it. Recorded in `test_data/products.json` as a `matches_by` field so it is not rediscovered by another failing test.

### 10.3 Test accounts are created through the API, not the signup UI

Registration is *setup* for the checkout and login journeys, not the thing under test. Driving a fifteen-field signup form through the browser for every checkout test would be slow, and would make a checkout failure indistinguishable from a signup failure.

**Decision:** the `registered_account` fixture creates a unique account through the site's own API and deletes it in teardown — even when the test fails, so runs leave no litter on a site other people share. Each account is unique, which is what lets tests run in parallel and in any order.

### 10.4 Fixture scoping favours independence over speed

The browser *process* is session-scoped, because launching one is expensive and it carries no test state. The browser **context**, the page, and the `requests` session are all function-scoped, so cookies and storage cannot leak between tests.

This is the concrete mechanism behind rule 3 (test independence) and is what makes `pytest -n` safe. Verified by running the full suite across four parallel workers.

### 10.5 Waits target `commit`, never `load`

**Discovered:** Phase 3, as a flaky failure under 4-way parallelism.

`wait_for_url` originally waited for the navigation's `load` event, which also waits on every subresource. This site embeds third-party ad frames that outlast a 30-second timeout under concurrent load, failing navigations that had actually succeeded.

**Decision:** `BasePage.wait_for_url` waits for `commit`; checkout and payment wait for the element the next step needs. Nothing is lost, because every Playwright locator call auto-waits for its own element. This turned one flaky failure into three consecutive clean parallel runs and made the suite 25% faster.

### 10.6 Response schemas live in `api_clients/`, not `test_data/`

JSON Schemas are not test *inputs* — they are the contract the API is expected to honour, and they belong to the layer that speaks to it. Each was derived from live responses rather than the site's prose documentation, which is why `price` is typed as a string (`"Rs. 500"`) rather than the number one might wish for.

### 10.7 Test data is loaded at import time, not through a fixture

`@pytest.mark.parametrize` needs its cases at *collection* time, before any fixture runs. A fixture-based loader would force every data-driven test into a loop inside one test function, collapsing a dozen independent cases into a single pass/fail. `test_data/loader.py` loads at import and caches; `case_ids()` surfaces each record's `id` so failures read `sql-injection-attempt` rather than `case2`.

### 10.8 Failure artifacts are captured in the `call` phase, not fixture teardown

The obvious place is fixture teardown, and that was the first implementation. But Allure files teardown attachments under the fixture's "Tear down" container, putting the screenshot two clicks away from the failure it explains — verified against the generated result JSON.

**Decision:** capture happens in `pytest_runtest_makereport` during the call phase, where the page is still open and Allure attributes attachments to the test itself. Capture never raises: if the browser has already crashed, the problem is attached as a note rather than thrown, so a diagnostic failure cannot mask the real one.

### 10.9 Additions to the stack

| Addition | Why |
|---|---|
| `pytest-rerunfailures` | The project's goal of separating real failures from flaky ones needs a mechanism. A test that fails then passes on rerun is the definition of flaky. Enabled in CI (`--reruns 1`), not locally. |
| `.gitattributes` | Development is on Windows, CI on Linux. Without LF normalization every commit carries CRLF into the repository and diffs fill with whole-file changes. |
| `test_data/checkout.yaml` | The data design in section 4 predates the checkout journey; card and order inputs needed a home to satisfy the no-hardcoded-inputs rule. |

### 10.10 Documentation naming

Section 3's folder structure listed `CLAUDE.md`; the build instructions call for `ARCHITECTURE.md`. These are different artifacts — one is agent instructions, the other a design record.

**Decision:** this file, renamed from `QAVigil_Architecture_Plan.md` to `ARCHITECTURE.md`, is the single design record. No `CLAUDE.md` is maintained.

### 10.11 Python version

The plan says "Python 3.11+". Three interpreters were available locally (3.11, 3.12, 3.14).

**Decision:** 3.12. It is in-spec, every pinned dependency has stable wheels for it, and it is a first-class GitHub Actions runner version, so local and CI agree. 3.14 was avoided as too new for the dependency set.

### 10.12 Phase 7 keeps its dependencies out of the core suite

`google-cloud-bigquery`, `streamlit`, `pandas` and `altair` live in `analytics/requirements.txt`, never the project's `requirements.txt`, and `google.cloud.bigquery` is imported lazily in both analytics modules. Someone cloning this repo to run tests must not have to install a cloud SDK, and the CI test job must not slow down for one. The CI export step installs only the BigQuery client, not the dashboard's dependencies.

### 10.13 Retries are collapsed before export, and flaky counts as a pass

Allure writes one result file per attempt, and `pytest-rerunfailures` produces several for a flaky test. Exported raw, **one flaky test would appear as both a failure and a pass**, quietly corrupting every pass-rate figure the dashboards show. `collapse_retries()` groups attempts by their shared `historyId`: if any attempt failed and the final one passed, the row is recorded as `flaky`, with duration summed across attempts.

The dashboard then counts `flaky` as a **pass** in the pass-rate line — it did pass — and gives flakiness its own chart. Folding flakes into the failure line would make the headline metric swing on infrastructure noise, which is how a dashboard teaches people to ignore it.

### 10.14 `--clean-alluredir` is mandatory, not tidiness

Found while testing the exporter: results accumulate across local runs, and because retries are correlated by `historyId`, the *same test from two different runs* looked like one flaky test with a retry. The exporter reported phantom retries on passing tests. CI gets a fresh checkout so it would not have been bitten, but relying on that is fragile — `--clean-alluredir` in `pytest.ini` makes local runs behave like CI.

### 10.15 The analytics export never fails the build

A BigQuery outage must not turn a green test run red. The tests' verdict is what matters; a build that fails over telemetry teaches people to ignore CI. On upload failure the exporter writes its rows to JSONL so the run's history can be loaded later, warns, and exits zero.

### 10.16 Two BigQuery credentials, never one

The export step's credential is write-scoped (`bigquery.dataEditor` on the single dataset) and lives in CI secrets; the dashboard's is read-only (`bigquery.dataViewer`) and lives in a deployed web app. Neither should be able to do the other's job. This is section 6's rule, made concrete in `analytics/README.md`.

### 10.17 The dashboard authenticates from Streamlit secrets, with ADC as fallback

**This was a defect in the first Phase 7 implementation, found by review rather than by testing.** `dashboard_app.py` read only `os.getenv` and called `bigquery.Client(project=...)`, which relies on Application Default Credentials. Streamlit Community Cloud has none, and there is nowhere to put a key *file*, so a deployed dashboard could never have authenticated. It would have failed, caught its own exception, and silently shown the empty state — the local JSONL verification I ran never exercised that path.

Streamlit promotes only top-level `str`/`int`/`float` secrets into `os.environ`, so `BQ_PROJECT`/`BQ_DATASET`/`BQ_TABLE` were reachable, but a service-account key is a nested TOML table and is not promoted. It has to be read through `st.secrets`.

`build_bigquery_client()` now prefers the `gcp_service_account` secret via `service_account.Credentials.from_service_account_info()`, and falls back to ADC when it is absent — which is the normal case on a laptop with `gcloud auth`, or on a GCP host. `service_account_info()` swallows the exception `st.secrets` raises when no secrets file exists at all, because absence is a supported state, not an error: `streamlit run` must keep working against the local JSONL with no secrets of any kind.

Read-only access is enforced by the credential's `bigquery.dataViewer` IAM role, not by application code. The failure message names which credential was attempted, since "could not read BigQuery" is ambiguous and a missing secret is by far the likeliest cause on a deployed app.

### 10.18 `db-dtypes` is an explicit dependency of the dashboard

`google-cloud-bigquery` imports `db-dtypes` *optionally* and raises `ValueError: Please install the 'db-dtypes' package` only when `RowIterator.to_dataframe()` is actually called. Nothing surfaces at import time, so a deploy looks healthy right up until someone opens a chart — which is exactly how it was found, in a real deployment rather than in testing.

It is pinned in `analytics/requirements.txt`. The CI export step deliberately does not install it: `export_to_bigquery.py` uses `insert_rows_json` and never touches pandas.

This is the second defect in the same blind spot as §10.17 — the BigQuery read path cannot be exercised without a real dataset, so local verification against the JSONL fallback passed while the deployed path was broken. Both failures degraded quietly rather than loudly, which is the property that let them ship. The `except Exception` in `load_data()` does cover this error class (verified by injecting the exact `ValueError`), so the dashboard falls back to the local export rather than crashing.

### 10.19 Python version is pinned for deployment hosts, but Streamlit Cloud's UI wins

`runtime.txt` at the repo root pins `python-3.12`, matching CI and local development. It is honoured by hosts that read the convention (Render, Heroku). Streamlit Community Cloud's authoritative setting is the Python selector in its deploy dialog, so the file records intent rather than guaranteeing the version there — stated plainly in `analytics/README.md` so nobody assumes the pin is doing more than it is.

### 10.20 Dashboard chart choices

Colours are drawn from a validated palette and checked with a colour-vision-deficiency and contrast validator in both light and dark modes (worst adjacent CVD ΔE 24.7 light / 26.8 dark, all six checks passing). Status meaning always carries a text label, never hue alone; a table view backs every chart. The pass-rate axis is deliberately not zero-based — a suite living between 95% and 100% shows nothing useful on a 0–100 axis — and headline figures are stat tiles rather than charts, because a single value is not a chart.

### 10.21 Manual steps CI cannot perform

Publishing to GitHub Pages requires **Settings → Pages → Source: GitHub Actions** to be enabled by a repository admin. The workflow is written and ready; the setting is deliberately not automated, since repository settings are out of scope for this project's tooling.

Phase 7 adds more of these, all requiring accounts and web UIs: creating the GCP project/dataset/table, creating the two service accounts, adding the four repository secrets, building the Looker Studio report, and deploying the Streamlit app. The full checklist is at the end of `analytics/README.md`. Everything on the code side is built and verified against a local JSONL export, so the pipeline can be demonstrated end-to-end before any cloud account exists.
