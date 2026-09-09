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
