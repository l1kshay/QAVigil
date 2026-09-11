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

import html
import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSONL = PROJECT_ROOT / "reports" / "test_runs.jsonl"

# --- design tokens ----------------------------------------------------------
# "Instrument panel for a test suite": calm and exact. Colour is functional -
# it encodes pass / flaky / fail state and nothing else. There is no
# decorative colour anywhere, and no boxed cards; sections are separated by
# hairline rules.

SANS = "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"
MONO = "'IBM Plex Mono', ui-monospace, 'Cascadia Mono', Consolas, monospace"

#: Same faces, unquoted - Vega takes a plain comma-separated family list.
SANS_STACK = "IBM Plex Sans, system-ui, -apple-system, Segoe UI, sans-serif"
MONO_STACK = "IBM Plex Mono, ui-monospace, Consolas, monospace"

#: Status colours are identical in both themes on purpose - a failure is the
#: same red whatever the surface. Contrast was measured rather than eyeballed,
#: which constrains where they may be used: as chart marks, as state rules,
#: and as large figures (>=24px), but never as small body text, where
#: #C97A2B reaches only 3.10:1 on the light background. Alerts therefore tint
#: the background and take a coloured rule, keeping their body copy in --text
#: at 12.5:1 or better.
STATUS = {
    "pass": "#1F7A5C",
    "flaky": "#C97A2B",
    "fail": "#B23A2E",
}

THEMES = {
    "light": {
        "bg": "#F6F7F5",
        "text": "#1B2430",
        # Derived, not given: the brief's four tokens have no secondary ink,
        # and axis labels need one that still clears 4.5:1 (measured 5.61:1).
        "muted": "#5A646E",
        "accent": "#3A5A78",
        "border": "#D8DCD9",
        "tint": 0.10,
    },
    "dark": {
        "bg": "#12161C",
        "text": "#E4E7EA",
        "muted": "#9AA4AE",   # 7.17:1 on the dark background
        "accent": "#7DA0BE",
        "border": "#2A313A",
        "tint": 0.10,
    },
}


def _tint(hex_colour: str, background: str, alpha: float) -> str:
    """Flatten a translucent status colour onto the page background.

    Used for alert fills. Computing the blend here rather than relying on
    rgba() keeps the resulting colour knowable, which is what let the contrast
    of body text over each tint be measured up front.
    """
    fg = hex_colour.lstrip("#")
    bg = background.lstrip("#")
    channels = [
        round(int(fg[i:i + 2], 16) * alpha + int(bg[i:i + 2], 16) * (1 - alpha))
        for i in (0, 2, 4)
    ]
    return "#%02X%02X%02X" % tuple(channels)


STATUS_ORDER = ["passed", "flaky", "failed", "skipped"]


# ---------------------------------------------------------------------------
# presentation
# ---------------------------------------------------------------------------
def inject_custom_css(theme: str) -> None:
    """Apply the instrument-panel styling. Called once, near the top of main().

    Every selector below is a ``data-testid`` verified against the installed
    Streamlit (1.63.0) by inspecting the rendered DOM, not recalled - the
    emotion class names beside them (``st-emotion-cache-*``) are generated and
    churn between releases, so they are never used.

    Theming is driven by the ``theme`` argument rather than a CSS attribute
    selector. Streamlit 1.63 emits no ``data-theme`` on ``<html>``, ``<body>``
    or ``stApp`` - verified - and ``st.context.theme.type`` is documented as
    unreliable on first load and during a theme change. One explicit control,
    read in Python, is the only mechanism here that is actually deterministic.
    """
    t = THEMES[theme]
    tints = {k: _tint(c, t["bg"], t["tint"]) for k, c in STATUS.items()}

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');

        :root {{
            --bg: {t["bg"]};
            --text: {t["text"]};
            --muted: {t["muted"]};
            --accent: {t["accent"]};
            --border: {t["border"]};
            --status-pass: {STATUS["pass"]};
            --status-flaky: {STATUS["flaky"]};
            --status-fail: {STATUS["fail"]};
            --tint-pass: {tints["pass"]};
            --tint-flaky: {tints["flaky"]};
            --tint-fail: {tints["fail"]};
        }}

        /* --- surfaces ---------------------------------------------------
           The app chrome is restyled too, so the whole surface follows the
           one theme control instead of leaving native widgets on the light
           base that config.toml sets. */
        [data-testid="stApp"],
        [data-testid="stMain"],
        [data-testid="stHeader"] {{
            background: var(--bg);
            color: var(--text);
        }}
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"] {{
            background: var(--bg);
            border-right: 1px solid var(--border);
        }}

        /* --- type -------------------------------------------------------
           Sans is the default; mono is applied deliberately below, only to
           numbers and identifiers. */
        [data-testid="stApp"], [data-testid="stApp"] p,
        [data-testid="stApp"] label, [data-testid="stApp"] button,
        [data-testid="stHeading"], [data-testid="stWidgetLabel"] {{
            font-family: {SANS};
            color: var(--text);
        }}
        /* The family has to be restated on the heading elements themselves.
           Setting it on the stHeading container is not enough: Streamlit
           styles h1/h2/h3 directly, and that rule wins on the child. */
        [data-testid="stHeading"] h1,
        [data-testid="stHeading"] h2,
        [data-testid="stHeading"] h3,
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {{
            font-family: {SANS};
            font-weight: 600;
            letter-spacing: -0.01em;
            color: var(--text);
            /* 1.45, with margin. IBM Plex Sans requires 1.395em by its own
               usWin metrics (1025 + 275 over 1000 upm, read from the woff2).
               The earlier 1.3 came from a canvas measurement that reports the
               smaller hhea figure, so it was actually UNDER the requirement
               that Windows browsers apply. 1.55 leaves ~11% headroom rather
               than the ~4% that 1.45 gave, on the same reasoning as the
               wordmark: this element has already been mis-measured once. */
            line-height: 1.55;
            overflow: visible;
        }}
        [data-testid="stHeading"] h3 {{ font-size: 1.02rem; }}
        [data-testid="stCaptionContainer"] {{ color: var(--muted); }}

        /* Mono for raw values: inline code, dataframe cells, and anything
           explicitly marked as a figure or identifier. */
        [data-testid="stApp"] code,
        .qv-mono {{
            font-family: {MONO};
            font-variant-ligatures: none;
        }}
        [data-testid="stApp"] code {{
            background: transparent;
            color: var(--text);
            font-size: 0.86em;
            padding: 0;
        }}

        /* --- top status strip ------------------------------------------- */
        .qv-strip {{
            display: flex;
            align-items: baseline;
            overflow: visible;
            gap: 1.5rem;
            flex-wrap: wrap;
            padding: 0 0 0.55rem 0;
            border-bottom: 1px solid var(--border);
            margin-bottom: 1.1rem;
        }}
        .qv-strip .qv-name {{
            font-family: {SANS};
            font-weight: 600;
            font-size: 0.95rem;
            /* 1.75, not a tight fit. IBM Plex Sans's own metrics (read from
               the woff2 with fontTools, not from a rendered measurement)
               require 1.395em: usWinAscent 1025 + usWinDescent 275 over a
               1000 upm. Windows browsers use those win metrics for the inline
               box, while canvas fontBoundingBox reports the smaller hhea
               figure of 1.30em - which is why the local measurement in Phase
               8c read this element as safe. 1.75 leaves 25% headroom over the
               real requirement, so a fallback face with taller metrics during
               font load still cannot crop it. */
            line-height: 1.75;
            overflow: visible;
            color: var(--accent);
            letter-spacing: 0.01em;
        }}
        .qv-strip .qv-field {{
            font-family: {SANS};
            font-size: 0.78rem;
            color: var(--muted);
        }}
        .qv-strip .qv-val {{
            font-family: {MONO};
            font-size: 0.78rem;
            line-height: 1.75;
            color: var(--text);
        }}
        .qv-strip .qv-spacer {{ margin-left: auto; }}

        /* --- instrument strip -------------------------------------------
           No boxes, no shadows, no radius, no fill. Readings are separated
           by a hairline rule, the way gauges share a bezel. */
        .qv-instruments {{
            display: flex;
            align-items: stretch;
            width: 100%;
            border-bottom: 1px solid var(--border);
            margin: 0 0 1.4rem 0;
        }}
        .qv-inst {{
            flex: 1 1 0;
            padding: 0.15rem 1.3rem 1.05rem 0;
            border-right: 1px solid var(--border);
        }}
        .qv-inst:first-child {{ padding-left: 0; }}
        .qv-inst:last-child {{ border-right: none; }}
        .qv-inst .qv-read {{
            font-family: {MONO};
            font-size: 2.25rem;      /* >=24px: status colours clear 3:1 here */
            font-weight: 500;
            line-height: 1.40;        /* 1.30em required; margin for fallbacks */
            color: var(--text);
            font-variant-numeric: tabular-nums;
        }}
        .qv-inst .qv-read.is-pass {{ color: var(--status-pass); }}
        .qv-inst .qv-read.is-flaky {{ color: var(--status-flaky); }}
        .qv-inst .qv-read.is-fail {{ color: var(--status-fail); }}
        .qv-inst .qv-label {{
            font-family: {SANS};
            font-size: 0.78rem;
            font-weight: 400;
            color: var(--muted);
            margin-top: 0.22rem;
        }}
        .qv-inst .qv-delta {{
            font-family: {MONO};
            font-size: 0.74rem;
            color: var(--muted);
            margin-top: 0.1rem;
        }}

        /* --- hero ---------------------------------------------------------
           One figure at roughly 3x the size of the readings beside it. The
           sparkline sits immediately beneath with the gap closed, so the
           number and its history read as a single object. */
        .qv-hero {{ margin: -0.35rem 0 -0.5rem 0; }}
        .qv-hero .qv-hero-read {{
            font-family: {MONO};
            font-size: 6.5rem;
            font-weight: 500;
            /* IBM Plex Mono requires 1.30em (hhea, win and typo metrics all
               agree, read from the woff2). 1.40 leaves margin for a fallback
               mono face with taller metrics during font load. Was 0.95, then
               1.12, then 1.32 - each an underestimate from a rendered
               measurement rather than the font's own tables. */
            line-height: 1.40;
            letter-spacing: -0.035em;
            color: var(--text);
            font-variant-numeric: tabular-nums;
        }}
        .qv-hero .qv-hero-read.is-pass {{ color: var(--status-pass); }}
        .qv-hero .qv-hero-read.is-flaky {{ color: var(--status-flaky); }}
        .qv-hero .qv-hero-read.is-fail {{ color: var(--status-fail); }}
        .qv-hero .qv-hero-meta {{
            display: flex;
            align-items: baseline;
            gap: 0.9rem;
            margin-top: 0;
        }}
        .qv-hero .qv-hero-label {{
            font-family: {SANS};
            font-size: 0.9rem;
            color: var(--muted);
        }}
        .qv-hero .qv-hero-delta {{
            font-family: {MONO};
            font-size: 0.8rem;
            color: var(--muted);
        }}
        /* Pull the sparkline up against the figure it belongs to. */
        .qv-spark-anchor + div [data-testid="stVegaLiteChart"] {{
            margin-top: -0.35rem;
        }}

        /* --- run history table --------------------------------------------
           Plain HTML, so the tokens reach it. Hairline rules, no zebra fill,
           no card edge - the same treatment as everything else. Values are
           numbers and identifiers, so the body is mono; the header names are
           words, so they stay in sans. */
        .qv-table-wrap {{ overflow-x: auto; }}
        .qv-table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg);
            font-family: {MONO};
            font-size: 0.76rem;
            font-variant-numeric: tabular-nums;
        }}
        /* Streamlit's markdown styling puts a full border on th/td, which
           renders as a spreadsheet grid. Only the horizontal hairline is
           wanted, so the vertical edges are cleared explicitly. */
        .qv-table th, .qv-table td {{
            border-left: none;
            border-right: none;
            border-top: none;
        }}
        .qv-table th {{
            font-family: {SANS};
            font-size: 0.74rem;
            font-weight: 500;
            text-align: left;
            color: var(--muted);
            background: var(--bg);
            padding: 0.4rem 0.9rem 0.4rem 0;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
            line-height: 1.45;
        }}
        .qv-table td {{
            color: var(--text);
            background: var(--bg);
            padding: 0.34rem 0.9rem 0.34rem 0;
            border-bottom: 1px solid var(--border);
            white-space: nowrap;
            line-height: 1.40;
        }}
        .qv-table tbody tr:last-child td {{ border-bottom: none; }}

        /* --- section rule ------------------------------------------------ */
        .qv-rule {{
            border: 0;
            border-top: 1px solid var(--border);
            margin: 1.6rem 0 1.1rem 0;
        }}

        /* --- alerts ------------------------------------------------------
           Streamlit paints the fill on stAlertContainer, and signals the kind
           via a child testid (stAlertContentError etc) - both verified in the
           DOM. Body copy stays in --text over a 10% tint, measured at 12.5:1
           or better; the status colour carries meaning as the left rule.
           st.info is deliberately NOT given a status colour: an unconfigured
           dashboard is not a failing one. */
        [data-testid="stAlertContainer"] {{
            border-radius: 0;
            box-shadow: none;
            border: 1px solid var(--border);
            border-left: 3px solid var(--muted);
            background: var(--bg);
            color: var(--text);
            font-family: {SANS};
        }}
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {{
            background: var(--tint-pass);
            border-left-color: var(--status-pass);
        }}
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {{
            background: var(--tint-flaky);
            border-left-color: var(--status-flaky);
        }}
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {{
            background: var(--tint-fail);
            border-left-color: var(--status-fail);
        }}
        [data-testid="stAlertContainer"] p,
        [data-testid="stAlertContainer"] code {{ color: var(--text); }}

        /* --- charts ------------------------------------------------------
           Vega renders into stVegaLiteChart; a transparent chart background
           is set in the Altair config so the plot sits on the page rather
           than on a pasted-in white rectangle. */
        [data-testid="stVegaLiteChart"],
        [data-testid="stVegaLiteChart"] canvas,
        [data-testid="stVegaLiteChart"] svg {{
            background: transparent !important;
        }}

        /* --- expanders: every one, not just the sidebar's ------------------
           These rules were scoped to [data-testid="stSidebar"] in Phase 8c,
           which fixed the Diagnostics panel and left every other expander
           with the leak. There are two in this app - Diagnostics in the
           sidebar and Run history in the main area - and the scope is now
           global so a third would be covered on arrival. */
        [data-testid="stExpander"] details {{
            border: 1px solid var(--border);
            border-radius: 0;
            background: var(--bg);
            /* The details element itself kept the LIGHT ink, which anything
               not covered below would inherit. */
            color: var(--text);
        }}
        /* Streamlit fills the summary with rgba(166,173,159,0.15) - a wash
           derived from the light secondaryBackground - which reads as a pale
           bar on the dark surface. Replaced with the page background and a
           hairline, consistent with the no-cards rule. */
        [data-testid="stExpander"] summary {{
            font-family: {SANS};
            font-size: 0.82rem;
            font-weight: 500;
            color: var(--text) !important;
            background: var(--bg) !important;
            border-bottom: 1px solid var(--border);
            border-radius: 0 !important;
        }}
        [data-testid="stExpander"] summary * {{
            color: var(--text) !important;
        }}
        /* COLOUR is global - that is the leak being fixed, and it has to
           reach every expander. */
        [data-testid="stExpanderDetails"],
        [data-testid="stExpanderDetails"] * {{
            color: var(--text);
        }}
        /* TYPOGRAPHY is not. The mono readout treatment belongs to the
           sidebar diagnostics panel specifically. Phase 8d applied it to
           every expander, which also restyled widget labels that happen to
           sit inside one - the CSV download button's label came out in mono,
           though it is words, not a value. p/li/ul/ol are covered because
           the diagnostics render as markdown bullet lists, which is what made
           every value an <li> that inherited nothing and fell back to the
           light ink at 1.16:1. */
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] p,
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] li,
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] ul,
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] ol,
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] span {{
            font-family: {MONO};
            font-size: 0.74rem;
            line-height: 1.55;
            margin-bottom: 0.28rem;
        }}
        [data-testid="stSidebar"] [data-testid="stExpanderDetails"] strong {{
            font-family: {SANS};
            font-weight: 600;
            color: var(--muted);
        }}
        [data-testid="stExpanderDetails"] code {{
            font-family: {MONO};
            color: var(--text);
        }}
        [data-testid="stSidebar"] [data-testid="stMarkdown"] p {{
            font-size: 0.82rem;
        }}

        /* --- vertical rhythm ---------------------------------------------
           Streamlit reserves 96px above the first element and 16px between
           every block, and the 96px is not decoration: stHeader is an OPAQUE
           overlay, 60px tall at z-index 999990, painted on top of the page.
           Phase 8b cut this to 2.6rem/41.6px for a tighter fold and put the
           top strip 8px UNDERNEATH it - measured, stripUnderHeader: true -
           so the header painted over the wordmark's ascenders. Locally that
           is invisible because the header is the same colour as the page;
           on Streamlit Cloud, whose header carries extra chrome and is
           taller, it shows as clipped glyphs.

           5.5rem/88px clears the 60px header by 28px, which leaves room for
           a taller deployed header, and still beats Streamlit's 96px default.
           Do not reduce this below the header height again. */
        [data-testid="stMainBlockContainer"] {{
            padding-top: 5.5rem;
            padding-bottom: 2rem;
        }}
        [data-testid="stMain"] [data-testid="stVerticalBlock"] {{
            gap: 0.65rem;
        }}
        [data-testid="stHeading"] h1 {{
            font-size: 1.85rem;
            margin-bottom: 0.1rem;
        }}
        [data-testid="stCaptionContainer"] {{ margin-bottom: 0.35rem; }}
        .qv-strip {{ margin-bottom: 0.75rem; }}
        .qv-instruments {{ margin: 0.5rem 0 0.9rem 0; }}
        .qv-rule {{ margin: 1.1rem 0 0.8rem 0; }}

        /* --- sidebar multiselect -----------------------------------------
           Streamlit renders the control with the background from
           config.toml's *light* base, so in dark mode it appeared as a white
           box against the panel - the exact class of leftover default this
           pass exists to catch. Hooked via role="group", which is ARIA and
           stable, rather than a generated class name. */
        [data-testid="stMultiSelect"] div[role="group"] {{
            background: var(--bg) !important;
            border: 1px solid var(--border) !important;
            border-radius: 0 !important;
        }}
        /* Every span, not just the one carrying role="group". The chips are
           nested - an outer role="group" wrapper around the actual chip span -
           and the Phase 8b selector matched only the wrapper, leaving the chip
           itself on Streamlit's light accent (#3A5A78) in dark mode. Measured:
           the remove-x sat at 2.52:1. With the themed accent it is 6.61:1
           dark / 6.71:1 light. */
        [data-testid="stMultiSelectTagsContainer"] span {{
            background: var(--accent) !important;
            border-radius: 0 !important;
        }}
        [data-testid="stMultiSelect"] input,
        [data-testid="stMultiSelect"] div[role="group"] * {{
            color: var(--text);
        }}
        [data-testid="stMultiSelectTagsContainer"] span *,
        [data-testid="stMultiSelectTagsContainer"] button,
        [data-testid="stMultiSelectTagsContainer"] svg {{
            color: var(--bg) !important;
            fill: var(--bg) !important;
        }}

        /* --- buttons -------------------------------------------------------
           st.download_button rendered as stBaseButton-secondary with a
           hardcoded near-white fill (rgb(252,253,252)) in BOTH themes - 1.22:1
           text contrast on the dark surface, and even in light it was a shade
           off the page. Every button kind is covered here rather than the one
           that was reported, since the file gains widgets over time; there is
           currently one st.download_button and no st.button.

           Styled as a hairline control, not a filled pill: same no-cards rule
           as everything else. The hover state recolours the border and text -
           a real state change, not decoration - with no transition. */
        [data-testid="stDownloadButton"] button,
        [data-testid="stBaseButton-secondary"],
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-tertiary"] {{
            background: var(--bg) !important;
            color: var(--text) !important;
            border: 1px solid var(--border) !important;
            border-radius: 0 !important;
            font-family: {SANS};
            font-size: 0.8rem;
            box-shadow: none !important;
        }}
        [data-testid="stDownloadButton"] button:hover,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="stBaseButton-primary"]:hover,
        [data-testid="stBaseButton-tertiary"]:hover {{
            border-color: var(--accent) !important;
            color: var(--accent) !important;
        }}
        [data-testid="stDownloadButton"] button *,
        [data-testid="stBaseButton-secondary"] * {{
            color: inherit !important;
            font-family: {SANS} !important;
            font-size: 0.8rem !important;
        }}

        /* --- native icons -------------------------------------------------
           The sidebar collapse arrow, the expander chevrons and the select
           chevron all render as span[data-testid="stIconMaterial"], which
           carried rgba(27,36,48,0.6) - the LIGHT ink at 60% - and so vanished
           on the dark surface (1.2:1). Inheriting means each icon takes the
           colour of whatever themed element contains it, so the chips keep
           their --bg cross while the sidebar arrow takes --text. */
        [data-testid="stIconMaterial"] {{
            color: inherit !important;
            opacity: 1;
        }}
        [data-testid="stSidebarCollapseButton"],
        [data-testid="stSidebarCollapseButton"] * {{
            color: var(--text) !important;
        }}

        /* --- chart chrome --------------------------------------------------
           Hovering a chart raised Streamlit's element toolbar: "Show data",
           "Download as PNG", "Copy Vega-Lite spec", "Fullscreen". Verified in
           the DOM - there is no vega-embed action menu here, so this, not
           Vega's own actions, is the menu to remove. Scoped with :has() to
           chart elements only: the run-history table keeps its toolbar, where
           "Download as CSV" and "Search" are genuinely useful. */
        [data-testid="stElementContainer"]:has([data-testid="stVegaLiteChart"])
          [data-testid="stElementToolbar"],
        [data-testid="stFullScreenFrame"]:has([data-testid="stVegaLiteChart"])
          [data-testid="stElementToolbar"] {{
            display: none !important;
        }}

        /* --- focus -------------------------------------------------------
           Restated, not removed: nothing above clears an outline, and making
           the ring explicit in the accent colour keeps it visible against
           both surfaces. */
        [data-testid="stApp"] :focus-visible {{
            outline: 2px solid var(--accent);
            outline-offset: 2px;
        }}

        /* Streamlit's default deploy button and toolbar clutter the top
           strip; the header itself stays for the settings menu. */
        [data-testid="stAppDeployButton"] {{ display: none; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _esc(value: object) -> str:
    """Escape a value for the small HTML fragments rendered below."""
    return html.escape(str(value), quote=True)


def render_status_strip(last_run: object | None, source: str) -> None:
    """A thin top line: what this is, what it watches, when it last ran."""
    stamp = (
        last_run.strftime("%Y-%m-%d %H:%M UTC")
        if last_run is not None and pd.notna(last_run)
        else "no runs recorded"
    )
    st.markdown(
        f"""
        <div class="qv-strip">
          <span class="qv-name">QAVigil</span>
          <span class="qv-field">target <span class="qv-val">automationexercise.com</span></span>
          <span class="qv-field qv-spacer">last run <span class="qv-val">{_esc(stamp)}</span></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_instrument_strip(readings: list[dict]) -> None:
    """The headline figures, as gauges sharing a bezel rather than as cards.

    Each reading is ``{value, label, state?, delta?}``. ``state`` maps to a
    status colour and is set only where the number genuinely reports pass or
    flaky state - the test count and the duration are neutral, because
    neither is a verdict.
    """
    cells = []
    for r in readings:
        state = f" is-{r['state']}" if r.get("state") else ""
        delta = (
            f'<div class="qv-delta">{_esc(r["delta"])}</div>' if r.get("delta") else ""
        )
        cells.append(
            f'<div class="qv-inst">'
            f'<div class="qv-read{state}">{_esc(r["value"])}</div>'
            f'<div class="qv-label">{_esc(r["label"])}</div>'
            f"{delta}</div>"
        )
    st.markdown(
        f'<div class="qv-instruments">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def render_hero(value: str, label: str, state: str | None, delta: str | None) -> None:
    """The one figure the page is built around.

    Scale is the whole design move here: this figure is roughly three times
    the size of the readings beside it, so the eye lands on suite health
    before anything else. The other readings deliberately stay small - the
    contrast is what makes this one read as the headline.
    """
    state_class = f" is-{state}" if state else ""
    delta_html = (
        f'<span class="qv-hero-delta">{_esc(delta)}</span>' if delta else ""
    )
    st.markdown(
        f"""
        <div class="qv-hero">
          <div class="qv-hero-read{state_class}">{_esc(value)}</div>
          <div class="qv-hero-meta">
            <span class="qv-hero-label">{_esc(label)}</span>{delta_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_run_history(table: pd.DataFrame) -> None:
    """The run-history table, as themed HTML rather than st.dataframe.

    Why not st.dataframe: it renders through glide-data-grid into a *canvas*
    (verified - two canvas elements, cells exposed only as accessibility
    nodes), and takes its colours from Streamlit's theme object rather than
    from CSS. Since config.toml pins a single light base while this app
    toggles its own theme, the grid stayed light on a dark page and no
    stylesheet could reach it.

    Both documented escape hatches were tried and photographed:
    ``Styler.set_properties`` does recolour the body cells, but
    ``set_table_styles`` does not reach the header row or the gridlines, which
    stayed light. A half-themed table is still a clashing table, so the view
    is plain HTML, which the same tokens style as everything else.

    What this costs: the grid's built-in sort and column resize. The CSV
    download that lived in its toolbar is re-offered by the caller.
    """
    headers = "".join(f"<th>{_esc(c)}</th>" for c in table.columns)
    rows = []
    for _, row in table.iterrows():
        cells = []
        for col in table.columns:
            value = row[col]
            if isinstance(value, pd.Timestamp):
                shown = value.strftime("%Y-%m-%d %H:%M")
            elif value is None or (isinstance(value, float) and pd.isna(value)):
                shown = "-"
            elif isinstance(value, float):
                shown = f"{value:g}"
            else:
                shown = str(value)
            cells.append(f"<td>{_esc(shown)}</td>")
        rows.append(f"<tr>{''.join(cells)}</tr>")
    st.markdown(
        f'<div class="qv-table-wrap"><table class="qv-table">'
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def section_rule() -> None:
    """A hairline divider between sections, in place of a card edge."""
    st.markdown('<hr class="qv-rule">', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------
#: Streamlit secrets key holding the READ-ONLY service account, as a TOML table
#: whose keys mirror the downloaded JSON key's fields.
SERVICE_ACCOUNT_SECRET = "gcp_service_account"


def read_service_account() -> tuple[dict | None, str | None]:
    """The reader service account from Streamlit secrets, plus any real error.

    Returns ``(info, error)``. A missing secrets file is a normal, supported
    state - it is what every local JSONL-only run looks like - and reports
    ``(None, None)``.

    Anything else reports the error rather than hiding it. The previous version
    caught every exception and returned None, which meant a *malformed*
    ``gcp_service_account`` table was indistinguishable from an absent one: the
    app quietly fell back to credentials it did not have. Silent degradation is
    the failure mode this whole diagnostic exists to eliminate.
    """
    try:
        if SERVICE_ACCOUNT_SECRET not in st.secrets:
            return None, None
        return dict(st.secrets[SERVICE_ACCOUNT_SECRET]), None
    except Exception as exc:
        # Streamlit raises when no secrets file exists at all. That is expected
        # and is not worth reporting; anything else is.
        if type(exc).__name__ in {
            "StreamlitSecretNotFoundError", "FileNotFoundError"
        }:
            return None, None
        return None, f"{type(exc).__name__}: {exc}"


def service_account_info() -> dict | None:
    """Just the service account, for callers that do not need the error."""
    info, _ = read_service_account()
    return info


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


def load_data() -> tuple[pd.DataFrame, str, dict]:
    """Load history from whichever source is configured, and record how.

    The third return value is a diagnostics record. It exists because this
    function has several ways to legitimately return an empty frame - config
    absent, query returned nothing, query failed - and the caller previously
    could not tell them apart. Everything the sidebar needs to explain an empty
    dashboard is captured here, at the moment it is known.
    """
    project = os.getenv("BQ_PROJECT")
    dataset = os.getenv("BQ_DATASET")
    table = os.getenv("BQ_TABLE", "test_runs")

    sa_info, sa_error = read_service_account()
    try:
        secret_keys = sorted(st.secrets.keys())
        secrets_readable = True
    except Exception:
        secret_keys, secrets_readable = [], False

    diag: dict = {
        # Values, not just presence: a typo in a project or dataset name is a
        # top suspect, and these are identifiers rather than credentials.
        "BQ_PROJECT": project,
        "BQ_DATASET": dataset,
        "BQ_TABLE": table,
        "bigquery_configured": bool(project and dataset),
        "secrets_readable": secrets_readable,
        # Names only. Never values - one of these tables holds a private key.
        "secret_keys": secret_keys,
        "service_account_secret_found": sa_info is not None,
        "service_account_fields": sorted(sa_info.keys()) if sa_info else [],
        "service_account_error": sa_error,
        "path": None,
        "auth_method": None,
        "rows_returned": None,
        "exception": None,
        "jsonl_path": str(DEFAULT_JSONL),
        "jsonl_exists": DEFAULT_JSONL.exists(),
    }

    if diag["bigquery_configured"]:
        diag["path"] = "bigquery"
        try:
            frame, auth_method = load_from_bigquery(project, dataset, table)
            diag["auth_method"] = auth_method
            diag["rows_returned"] = len(frame)
            return frame, f"BigQuery ({dataset}.{table}, via {auth_method})", diag
        except Exception as exc:
            diag["exception"] = f"{type(exc).__name__}: {exc}"
            diag["path"] = "bigquery -> failed, fell back to local file"
            st.warning(
                f"{explain_bigquery_failure(exc)} Falling back to the local export."
            )
    else:
        diag["path"] = "local file (BigQuery not configured)"

    frame = load_from_jsonl(str(DEFAULT_JSONL))
    diag["rows_returned"] = len(frame)
    return frame, f"local file ({DEFAULT_JSONL.name})", diag


def render_diagnostics(diag: dict) -> None:
    """Show how the data was (or was not) loaded.

    Always rendered, including when the frame is empty - which is precisely
    when it is needed. Shows key *names* and booleans only; no secret value is
    ever displayed.
    """
    with st.sidebar:
        with st.expander("Diagnostics", expanded=not diag.get("rows_returned")):
            st.markdown(
                f"**Path taken:** `{diag['path']}`\n\n"
                f"**Rows returned:** `{diag['rows_returned']}`"
            )

            st.markdown("**Environment (read at runtime)**")
            st.markdown(
                f"- `BQ_PROJECT` = `{diag['BQ_PROJECT'] or '(unset)'}`\n"
                f"- `BQ_DATASET` = `{diag['BQ_DATASET'] or '(unset)'}`\n"
                f"- `BQ_TABLE` = `{diag['BQ_TABLE'] or '(unset)'}`\n"
                f"- BigQuery configured: `{diag['bigquery_configured']}`"
            )

            st.markdown("**Streamlit secrets** (names only, never values)")
            st.markdown(
                f"- readable: `{diag['secrets_readable']}`\n"
                f"- top-level keys: `{diag['secret_keys'] or '(none)'}`\n"
                f"- `{SERVICE_ACCOUNT_SECRET}` found: "
                f"`{diag['service_account_secret_found']}`\n"
                f"- its fields: `{diag['service_account_fields'] or '(n/a)'}`"
            )
            if diag["service_account_error"]:
                st.error(
                    "Reading the service-account secret failed: "
                    f"`{diag['service_account_error']}`"
                )

            if diag["auth_method"]:
                st.markdown(f"**Authenticated via:** `{diag['auth_method']}`")

            if diag["exception"]:
                st.error(f"**Exception caught:** `{diag['exception']}`")

            st.markdown(
                f"**Local fallback file:** `{diag['jsonl_path']}` "
                f"(exists: `{diag['jsonl_exists']}`)"
            )


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
    """Shared Vega config, matched to the page rather than to Vega's defaults.

    Three things make a chart stop looking pasted in: a transparent background
    so it sits on the page, axis type that matches the surrounding UI, and a
    recessive grid. Tick labels are dates and numbers, so they take the mono
    face; axis and legend *titles* are words, so they stay in sans.
    """
    return {
        "background": "transparent",
        "axis": {
            "domainColor": colors["accent"],
            "domainWidth": 1,
            "gridColor": colors["border"],
            "gridWidth": 1,
            "tickColor": colors["accent"],
            "labelColor": colors["muted"],
            "labelFont": MONO_STACK,
            "labelFontSize": 11,
            "titleColor": colors["muted"],
            "titleFont": SANS_STACK,
            "titleFontSize": 11,
            "titleFontWeight": "normal",
            "titlePadding": 8,
        },
        "legend": {
            "labelColor": colors["text"],
            "labelFont": SANS_STACK,
            "titleColor": colors["muted"],
            "titleFont": SANS_STACK,
            "labelFontSize": 12,
            "titleFontSize": 11,
            "titleFontWeight": "normal",
        },
        "view": {"stroke": "transparent"},
    }


#: vega-embed reads embed options from the spec's ``usermeta``. Verified that
#: st.altair_chart has no embed_options parameter in Streamlit 1.63, and that
#: usermeta round-trips into the compiled spec, so this is the supported route
#: rather than a remembered kwarg. Belt-and-braces: the DOM check found no
#: vega-embed action menu locally - the menu seen on the deployment is
#: Streamlit's own element toolbar, hidden in CSS - but if any environment does
#: render Vega's actions, this suppresses them at the source.
NO_ACTIONS = {"embedOptions": {"actions": False}}


def _finish(chart: alt.Chart, colors: dict[str, str], height: int) -> alt.Chart:
    """Apply the shared config, height and embed options to every chart."""
    return (
        chart.properties(height=height, usermeta=NO_ACTIONS)
        .configure(**_base(colors))
    )


def _rgba(hex_colour: str, alpha: float) -> str:
    """A status colour at a given alpha, for gradient stops."""
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _area_gradient(colour: str) -> alt.Gradient:
    """A vertical fade from the line down to nothing at the baseline.

    The fill is weight, not decoration: a bare stroke on a flat series reads
    as an empty chart, while an area anchored to the baseline shows the
    magnitude the line is sitting at.
    """
    return alt.Gradient(
        gradient="linear",
        x1=0, x2=0, y1=0, y2=1,
        stops=[
            alt.GradientStop(color=_rgba(colour, 0.38), offset=0),
            alt.GradientStop(color=_rgba(colour, 0.0), offset=1),
        ],
    )


def hero_sparkline(
    summary: pd.DataFrame, colors: dict[str, str], colour: str
) -> alt.Chart:
    """The pass-rate series as a full-width sparkline under the hero figure.

    Driven by the same data as the pass-rate chart below, not a drawn shape.
    With one or two runs recorded it will look sparse, which is honest: the
    dots are the runs there actually are.
    """
    base = alt.Chart(summary)
    area = base.mark_area(
        line={"color": colour, "strokeWidth": 2},
        color=_area_gradient(colour),
    ).encode(
        # No axes at all: the hero figure states the current value, and the
        # chart below carries the labelled, zero-based version.
        x=alt.X("run_timestamp:T", axis=None, title=None),
        # Deliberately NOT zero-based, unlike the chart below. A sparkline's
        # job is the shape of the trend, and a zero baseline flattens a series
        # that lives near 100 into a straight line that shows nothing. Nobody
        # reads magnitude off an unlabelled strip, so the usual objection to a
        # non-zero area baseline does not apply here.
        y=alt.Y(
            "pass_rate:Q",
            axis=None,
            title=None,
            scale=alt.Scale(zero=False, domainMax=100, nice=False),
        ),
    )
    points = base.mark_point(
        color=colour, size=26, filled=True, opacity=1,
    ).encode(
        x=alt.X("run_timestamp:T", axis=None),
        y=alt.Y("pass_rate:Q", axis=None),
        tooltip=[
            alt.Tooltip("run_timestamp:T", title="Run at"),
            alt.Tooltip("pass_rate:Q", title="Pass rate (%)"),
        ],
    )
    return _finish(area + points, colors, 104)


def pass_rate_chart(summary: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Pass rate over time. One series, so no legend - the title names it."""
    hover = alt.selection_point(
        fields=["run_timestamp"], nearest=True, on="pointerover", empty=False
    )

    area = (
        alt.Chart(summary)
        .mark_area(
            line={"color": STATUS["pass"], "strokeWidth": 2},
            color=_area_gradient(STATUS["pass"]),
        )
        .encode(
            x=alt.X(
                "run_timestamp:T",
                title="Run",
                axis=alt.Axis(format="%b %d", labelAngle=0, tickCount="day"),
            ),
            # Zero-based, and stated explicitly rather than left to Vega.
            # This used to be a line with zero=False, because a series living
            # near 100 shows nothing on a 0-100 axis. Now that it is an area,
            # that reasoning inverts: an area filling to a non-zero baseline
            # misstates the magnitude it appears to show. The precision that
            # costs is carried by the hero figure above, which states the
            # current value exactly.
            y=alt.Y(
                "pass_rate:Q",
                title="Pass rate (%)",
                scale=alt.Scale(domain=[0, 100], nice=False),
            ),
        )
    )

    # Always drawn, not just on hover. A flat line with no markers reads as an
    # empty chart; a dot per run says "these are the runs there have been".
    points = (
        alt.Chart(summary)
        .mark_point(
            color=STATUS["pass"], size=34, filled=True, opacity=1,
            stroke=colors["bg"], strokeWidth=1,
        )
        .encode(x="run_timestamp:T", y="pass_rate:Q")
    )

    # A second, larger marker that appears under the cursor and carries the
    # tooltip - it responds to a real state change rather than decorating a
    # static element.
    hover_points = (
        alt.Chart(summary)
        .mark_point(
            color=STATUS["pass"], size=110, filled=True,
            stroke=colors["bg"], strokeWidth=2,
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

    # 170, down from 260: a rate series that mostly sits near 100 does not
    # carry enough visual information to justify a third of the page.
    return _finish(area + points + hover_points, colors, 170)


def flaky_chart(board: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Flaky frequency. Horizontal bars: long test names need horizontal room."""
    return (
        alt.Chart(board)
        .mark_bar(color=STATUS["flaky"], height=14)
        .encode(
            # Integer run counts, so integer ticks - 3.5 runs is not a thing.
            x=alt.X(
                "occurrences:Q",
                title="Runs in which it flaked",
                axis=alt.Axis(tickMinStep=1, format="d"),
            ),
            y=alt.Y(
                "short_name:N",
                title=None,
                sort="-x",
                axis=alt.Axis(labelLimit=260, labelPadding=8),
            ),
            tooltip=[
                alt.Tooltip("test_name:N", title="Test"),
                alt.Tooltip("occurrences:Q", title="Runs flaked"),
                alt.Tooltip("retries:Q", title="Total retries"),
            ],
        )
        # Step, not a total height: `height=N` divides N across however many
        # bars there are, so a short leaderboard squeezed its bands to ~20px
        # and Vega drew the test names on top of each other. Step fixes the
        # height *per band*, so rows stay legible at any row count.
        .properties(height=alt.Step(40), usermeta=NO_ACTIONS)
        .configure(**_base(colors))
    )


def duration_chart(durations: pd.DataFrame, colors: dict[str, str]) -> alt.Chart:
    """Suite duration over time. Two series, so a legend is always present."""
    return (
        alt.Chart(durations)
        .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=45, filled=True))
        .encode(
            x=alt.X(
                "run_timestamp:T",
                title="Run",
                axis=alt.Axis(format="%b %d", labelAngle=0, tickCount="day"),
            ),
            y=alt.Y("duration_seconds:Q", title="Duration (seconds)"),
            color=alt.Color(
                "suite:N",
                title="Suite",
                scale=alt.Scale(
                    domain=["ui", "api", "environment"],
                    range=[colors["accent"], colors["muted"], colors["border"]],
                ),
            ),
            tooltip=[
                alt.Tooltip("run_timestamp:T", title="Run at"),
                alt.Tooltip("suite:N", title="Suite"),
                alt.Tooltip("duration_seconds:Q", title="Seconds", format=".1f"),
            ],
        )
        .properties(height=260, usermeta=NO_ACTIONS)
        .configure(**_base(colors))
    )


# ---------------------------------------------------------------------------
# app
# ---------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="QAVigil - suite health", layout="wide")

    # The theme control is read before anything renders, because the CSS it
    # selects has to be in the document before the first painted element.
    with st.sidebar:
        st.header("View")
        theme = st.radio("Theme", ["light", "dark"], horizontal=True)
    colors = THEMES[theme]
    inject_custom_css(theme)

    raw, source, diag = load_data()

    # The strip needs the newest run, which is only known once data is loaded.
    last_run = None
    if not raw.empty and "run_timestamp" in raw:
        last_run = pd.to_datetime(
            raw["run_timestamp"], utc=True, format="mixed", errors="coerce"
        ).max()
    render_status_strip(last_run, source)

    st.title("QAVigil suite health")
    st.caption(
        "Pass rate, flakiness and duration across test runs of "
        "automationexercise.com."
    )

    # Rendered before the early return below. The previous version computed
    # `source` and then returned without ever showing it, so the one case that
    # needed an explanation was the one case that got none.
    render_diagnostics(diag)

    if raw.empty:
        # Report the cause rather than asserting one. This message used to say
        # "or set BQ_PROJECT and BQ_DATASET", which is only correct on one of
        # the three paths that reach here - and reads as a confident diagnosis
        # on the other two.
        if diag["path"].startswith("bigquery") and diag["exception"] is None:
            st.warning(
                f"The query against `{diag['BQ_DATASET']}.{diag['BQ_TABLE']}` "
                "succeeded but returned **zero rows**. The credential and the "
                "connection are fine - either the table is empty, or "
                "`BQ_PROJECT`/`BQ_DATASET`/`BQ_TABLE` point somewhere other "
                "than where the exporter writes. See Diagnostics in the sidebar."
            )
        elif diag["exception"] is not None:
            st.warning(
                "BigQuery could not be read and the local fallback file is "
                "absent, so there is nothing to show. The cause is in the "
                "warning above and in Diagnostics in the sidebar."
            )
        else:
            st.info(
                "No run history yet, and BigQuery is not configured "
                f"(`BQ_PROJECT`={diag['BQ_PROJECT'] or 'unset'}, "
                f"`BQ_DATASET`={diag['BQ_DATASET'] or 'unset'}).\n\n"
                "Generate some locally with:\n\n"
                "```\npytest\npython analytics/export_to_bigquery.py --dry-run\n```"
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
    # reading, not a chart. Rendered as one instrument strip rather than four
    # st.metric cards: a boxed card implies each number is a separate object,
    # when in fact they are four readings off the same run.
    #
    # Colour is applied only where the number is a verdict. Pass rate and
    # flaky count are; the test count and the duration are measurements, so
    # they stay in --text. Anything else would be colour used decoratively.
    flaky_count = int(latest["flaky"])
    pass_state = "pass" if latest["pass_rate"] >= 100 else "flaky"

    # The hero, and its real history immediately beneath it.
    render_hero(
        value=f"{latest['pass_rate']:.1f}%",
        label="Pass rate, latest run",
        state=pass_state,
        delta=(
            f"{latest['pass_rate'] - previous['pass_rate']:+.1f} pts vs previous"
            if previous is not None else None
        ),
    )
    st.markdown('<div class="qv-spark-anchor"></div>', unsafe_allow_html=True)
    st.altair_chart(
        hero_sparkline(summary, colors, STATUS[pass_state]),
        use_container_width=True,
    )

    render_instrument_strip([
        {"value": int(latest["tests"]), "label": "Tests in run"},
        {
            "value": flaky_count,
            "label": "Flaky, latest run",
            "state": "flaky" if flaky_count else None,
            "delta": (
                f"{flaky_count - int(previous['flaky']):+d} vs previous"
                if previous is not None else None
            ),
        },
        {
            "value": f"{latest['duration_seconds']:.0f}s",
            "label": "Duration, latest run",
        },
    ])

    st.subheader("Pass rate over time")
    st.altair_chart(pass_rate_chart(summary, colors), use_container_width=True)

    section_rule()

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

    section_rule()

    # A table view is the accessibility fallback for every chart above, and the
    # thing anyone will want when a chart raises a question it cannot answer.
    with st.expander("Run history (table view)"):
        table = summary[
            ["run_timestamp", "run_id", "branch", "tests", *STATUS_ORDER,
             "pass_rate", "duration_seconds"]
        ]
        render_run_history(table)
        # st.dataframe carried a CSV download in its toolbar; rendering the
        # table as HTML loses that, so it is offered explicitly rather than
        # quietly dropped.
        st.download_button(
            "Download run history as CSV",
            data=table.to_csv(index=False).encode("utf-8"),
            file_name="qavigil_run_history.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
