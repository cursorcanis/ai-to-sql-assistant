"""
Measure Studio — a text-to-code interface, rendered in Streamlit.

The subject is deliberately narrow: describe a business metric in plain
English, get the DAX and T-SQL that implement it. A portfolio piece works
harder when it demonstrates the domain, not just the framework.

Swap `generate()` for a real model call when you're ready. Everything else
is the interaction design.
"""

import time
import streamlit as st
from theme import inject

st.set_page_config(
    page_title="Measure Studio",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject()

# --- Canned generations. Replace with your model call. --------------------
EXAMPLES = {
    "rolling 90-day active households, excluding duplicates": {
        "dax": """Active Households 90D =
VAR _Window =
    DATESINPERIOD(
        'Date'[Date],
        MAX ( 'Date'[Date] ),
        -90,
        DAY
    )
RETURN
    CALCULATE (
        DISTINCTCOUNT ( Enrollment[HouseholdKey] ),
        _Window,
        Enrollment[IsDuplicate] = FALSE ()
    )""",
        "sql": """SELECT
    d.CalendarDate,
    COUNT(DISTINCT e.HouseholdKey) AS ActiveHouseholds90D
FROM dbo.DimDate AS d
LEFT JOIN dbo.FactEnrollment AS e
    ON  e.EnrollmentDate > DATEADD(DAY, -90, d.CalendarDate)
    AND e.EnrollmentDate <= d.CalendarDate
    AND e.IsDuplicate = 0
WHERE d.CalendarDate BETWEEN @StartDate AND @EndDate
GROUP BY d.CalendarDate
ORDER BY d.CalendarDate;""",
        "notes": [
            ("Grain", "one row per calendar date"),
            ("Window", "trailing 90 days, inclusive of current"),
            ("Assumption", "`IsDuplicate` resolved upstream in the enrollment feed"),
        ],
    }
}
DEFAULT = list(EXAMPLES)[0]


def generate(prompt: str):
    """Stand-in for the model call. Returns the same shape either way."""
    return EXAMPLES.get(prompt.strip().lower(), EXAMPLES[DEFAULT])


def stream(text: str, cps: int = 900):
    """Reveal code at a readable rate. The wait is the proof of work —
    an instant result reads as a lookup, not a generation."""
    step = max(1, len(text) // 60)
    for i in range(0, len(text) + step, step):
        yield text[:i]
        time.sleep(step / cps)
    yield text


# --- Header ---------------------------------------------------------------
st.markdown('<div class="eyebrow">Alea Artificium · Semantic layer tooling</div>',
            unsafe_allow_html=True)
st.markdown("# Measure Studio")
st.markdown(
    '<p class="lede">Describe a metric the way you would to an analyst. '
    'Get the DAX measure and the equivalent T-SQL, with the grain and '
    'assumptions stated explicitly.</p>',
    unsafe_allow_html=True,
)
st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

left, right = st.columns([0.42, 0.58], gap="large")

# --- Prompt side ----------------------------------------------------------
with left:
    st.markdown('<div class="eyebrow">Prompt</div>', unsafe_allow_html=True)
    prompt = st.text_area(
        "Metric description",
        value=DEFAULT,
        height=150,
        label_visibility="collapsed",
        placeholder="e.g. median days to housing placement, by CoC region",
    )
    c1, c2 = st.columns([1, 1])
    run = c1.button("Generate", type="primary", use_container_width=True)
    c2.button("Clear", use_container_width=True)

    st.markdown('<div class="rule"></div>', unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">Model context</div>', unsafe_allow_html=True)
    st.markdown(
        '<span class="chip">DimDate</span><span class="chip">FactEnrollment</span>'
        '<span class="chip">DimHousehold</span><span class="chip">DimProgram</span>',
        unsafe_allow_html=True,
    )

# --- Output side ----------------------------------------------------------
with right:
    st.markdown('<div class="eyebrow">Output</div>', unsafe_allow_html=True)

    if run or "result" not in st.session_state:
        st.session_state.result = generate(prompt)
        fresh = run
    else:
        fresh = False

    res = st.session_state.result
    tab_dax, tab_sql, tab_notes = st.tabs(["DAX", "T-SQL", "Assumptions"])

    with tab_dax:
        if fresh:
            slot = st.empty()
            for partial in stream(res["dax"]):
                slot.code(partial, language="dax")
        else:
            st.code(res["dax"], language="dax")

    with tab_sql:
        st.code(res["sql"], language="sql")

    with tab_notes:
        for label, value in res["notes"]:
            st.markdown(
                f'<div style="display:flex;gap:1rem;padding:0.5rem 0;'
                f'border-bottom:1px solid var(--line-soft)">'
                f'<span class="meta" style="min-width:90px">{label}</span>'
                f'<span style="font-size:0.85rem;color:var(--muted)">{value}</span></div>',
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="meta" style="margin-top:0.9rem">'
        '<span class="dot" style="background:var(--ok)"></span> '
        '&nbsp;Validated against model · 4 tables in scope</div>',
        unsafe_allow_html=True,
    )
