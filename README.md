# QAVigil

CI-integrated UI + API test automation framework (Playwright, Pytest, GitHub
Actions) built against a live demo e-commerce app.

The target under test is [automationexercise.com](https://automationexercise.com)
— a public demo store with both a real UI and a documented REST API. QAVigil
does not build or host that application; it tests it.

The full design rationale lives in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Requirements

- Python 3.11 or newer (developed and pinned against 3.12)
- Node.js — only if you want to generate the Allure HTML report locally

## Install

```bash
git clone https://github.com/l1kshay/QAVigil.git
cd QAVigil

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python -m playwright install chromium
```

Copy the environment template. The suite runs without it — every value has a
working default — but this is where you change the target or watch a run in a
real browser:

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

`.env` is gitignored and must never be committed. In CI these same keys come
from GitHub Actions Secrets.

| Key | Default | Purpose |
|---|---|---|
| `BASE_URL` | `https://automationexercise.com` | UI target |
| `API_BASE_URL` | `<BASE_URL>/api` | API target |
| `BROWSER` | `chromium` | `chromium`, `firefox` or `webkit` |
| `HEADLESS` | `true` | set `false` to watch the browser |
| `TIMEOUT_MS` | `30000` | per-action and per-navigation timeout |
| `SLOW_MO_MS` | `0` | raise to slow each action down and watch a run |
| `TEST_USER_EMAIL` | *(empty)* | optional pre-existing account |
| `TEST_USER_PASSWORD` | *(empty)* | optional pre-existing account |

The test account keys are optional. Tests that need a signed-in user create
their own throwaway account and delete it afterwards, so a fresh clone runs
green with no credentials at all.

## Run

```bash
pytest                             # everything
pytest -m smoke                    # fast, high-value subset
pytest -m regression               # the full suite
pytest tests/api                   # API only (no browser needed)
pytest tests/ui                    # UI only
pytest -n 4                        # 4 workers in parallel
pytest -k login                    # anything matching "login"
```

Parallel is the normal way to run this suite: ~58s across 4 workers versus
~2m30s serially. Every test is independent by construction, so `-n` is safe.

To watch a run in a real browser:

```bash
HEADLESS=false SLOW_MO_MS=300 pytest -m smoke -k checkout
```

## Markers

| Marker | Meaning | When it runs in CI |
|---|---|---|
| `smoke` | Fast, high-value checks. If these fail, something important broke. | Every push |
| `regression` | Full coverage, including edge cases and slow journeys. | Pull requests, and nightly |

Markers are `--strict`, so a typo in a marker name fails the run instead of
silently selecting nothing.

---

## Reading the report

Every run writes two reports into `reports/`:

**`reports/report.html`** — self-contained pytest-html output. Open it directly
in a browser. This is the fallback, and the one that always works locally.

**`reports/allure-results/`** — raw Allure results. Turning them into a report
needs the Allure CLI, which needs Java:

```bash
npm install -g allure-commandline
allure serve reports/allure-results        # opens in a browser
```

CI generates the Allure HTML for you and publishes it — see below.

### What a failing UI test gives you

A UI failure attaches four things to its Allure entry, on the test itself
rather than buried under a teardown section:

- **`screenshot-at-failure`** — full-page screenshot at the moment of failure
- **`url-at-failure`** — where the browser actually was, which is usually the
  answer when a test fails somewhere unexpected
- **`page-html-at-failure`** — the DOM at failure, for when a locator stopped
  matching
- **`playwright-trace`** — a complete recording: DOM snapshots, network,
  console, and sources. Download it and open it at
  [trace.playwright.dev](https://trace.playwright.dev). This is the tool that
  solves "it fails in CI but not on my machine."

None of these are produced for passing tests, deliberately — keeping traces for
green runs would cost hundreds of megabytes per run and bury the one that
matters.

### Where CI publishes it

- **Artifacts** — every run, pass or fail, uploads `test-report-<n>` containing
  the Allure HTML and `report.html`. Failing runs additionally upload
  `failure-artifacts-<n>` with the screenshots and traces.
- **GitHub Pages** — runs on `main` publish the Allure report to the repository's
  Pages site.

> **One-time setup:** GitHub Pages must be enabled with **Settings → Pages →
> Source: GitHub Actions** before the publish step can succeed. This repository's
> workflow is ready for it; the setting has to be flipped by a repo admin.

---

## Telling a real failure from a flaky one

The target is a live third-party demo site. It goes slow, serves ad iframes,
and occasionally rate-limits — none of which are bugs in the code under test,
but all of which can turn a test red.

Two things separate signal from noise:

1. **CI reruns a failing test once** (`--reruns 1`). A test that fails and then
   passes is flaky by definition; one that fails twice is a real failure and
   fails the build. The Allure report labels the retried ones.
2. **`tests/test_environment.py` runs first-class in the smoke set.** If the
   site is simply unreachable, those three checks fail and tell you the suite
   never got the chance to test anything — rather than leaving you to infer it
   from thirty confusing failures.

### Known flaky tests

Nothing in this suite is currently quarantined or expected to flake. The three
sources of instability found so far were all fixed at the root rather than
papered over with retries or sleeps:

| Symptom | Root cause | Fix |
|---|---|---|
| `test_placing_an_order_confirms_it` timed out waiting for `**/payment**` under 4-way parallelism | `wait_for_url` waited for the `load` event, which waits on *every* subresource; the site's third-party ad frames outlast the 30s timeout under concurrent load, even though the navigation itself had succeeded | Wait for `commit` instead, and have checkout/payment wait for the element the next step needs. Went from one flaky failure to three consecutive clean parallel runs, and 25% faster. |
| Cart modal's "Continue Shopping" click intermittently swallowed | The modal's fade-out animation intercepted the following click | `continue_shopping()` waits for the modal to reach the `hidden` state before returning |
| `test_search_results_are_relevant_to_the_term` failed on valid data | Not flakiness — a wrong assumption. The site matches on **category** as well as name, so "dress" correctly returns items whose names lack the word | Test rewritten to assert a true property; category relevance moved to the API suite, where the field exists |

If a test does start flaking, please add it here with its root cause rather
than only increasing a timeout.

---

## Project layout

```
pages/          Page Objects. One class per page, intent-named actions.
api_clients/    One client per API surface, plus the response schemas.
tests/ui/       Browser tests. No raw locators, no URLs.
tests/api/      API tests. No raw requests calls.
test_data/      YAML/JSON fixtures and their loader.
config/         Environment resolution.
reports/        Generated output (gitignored).
conftest.py     Shared fixtures.
```

### The rules this structure enforces

- Tests never contain a raw Playwright locator or a URL — they call Page Object
  methods.
- API tests never call `requests` directly — they go through `api_clients/`.
- No `sleep()` anywhere. Waits target conditions, never durations.
- Every test is independent and order-agnostic, which is what makes `-n` safe.
- No credentials in the repository. Valid accounts are generated per test.
- Every test-data record carries an explicit `expected_result` /
  `expected_status`.

### One thing to know before reading the code

**This API answers every request with HTTP 200** and reports the real status in
the response body's `responseCode` field. A missing parameter comes back as
`HTTP 200` with `{"responseCode": 400, ...}`.

That is why `ApiResponse.status` means the *body* code, and why `http_status` is
kept separately. A suite that asserted on `response.status_code` would see 200
everywhere and every negative test would pass without testing anything. The
assumption is asserted explicitly in
`tests/api/test_negative_cases.py::test_errors_are_reported_in_the_body_not_the_http_status`,
so if the site ever adopts real status codes, that test fails and says so
instead of the suite quietly going green.
