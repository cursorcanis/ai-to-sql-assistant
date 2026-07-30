"""
theme.py — the CSS layer.

config.toml handles palette, radius and type. Everything below is the part
Streamlit's theme API can't reach: density, chrome removal, focus states,
and the two or three details that separate "a Streamlit app" from "a product".

Call inject() once, immediately after st.set_page_config().
"""

import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --bg:        #0A0A0B;
  --surface:   #121214;
  --surface-2: #17171A;
  --line:      #26262A;
  --line-soft: #1C1C20;
  --text:      #ECECEE;
  --muted:     #8A8A93;
  --faint:     #5A5A63;
  --signal:    #8B93F8;
  --ok:        #4ADE80;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace;
  --ui:   'Inter Tight', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ---- 1. Strip the platform chrome ------------------------------------ */
#MainMenu, footer, [data-testid="stStatusWidget"] { visibility: hidden; height: 0; }
[data-testid="stHeader"] { background: transparent; height: 0; }
[data-testid="stDecoration"] { display: none; }

/* ---- 2. Density. Streamlit's defaults are generous to a fault. -------- */
.block-container {
  padding-top: 2.25rem;
  padding-bottom: 3rem;
  max-width: 1180px;
}
[data-testid="stVerticalBlock"] { gap: 0.65rem; }

/* ---- 3. Type scale. One display size, one body, one caption. ---------- */
html, body, [class*="css"] { font-family: var(--ui); }

h1 {
  font-size: 1.55rem !important;
  font-weight: 600 !important;
  letter-spacing: -0.022em;
  line-height: 1.15;
  margin-bottom: 0.15rem !important;
}
h2 { font-size: 1.05rem !important; font-weight: 600 !important; letter-spacing: -0.014em; }
h3 { font-size: 0.9rem  !important; font-weight: 600 !important; }

/* The eyebrow: monospace, uppercase, wide-tracked, faint. This single
   device does more for "professional tool" than any amount of gradient. */
.eyebrow {
  font-family: var(--mono);
  font-size: 0.66rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--faint);
  margin-bottom: 0.5rem;
}
.lede { color: var(--muted); font-size: 0.9rem; line-height: 1.55; }

/* ---- 4. Panels. Hairline borders, no shadows, no rounding beyond 4px. - */
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 1rem 1.1rem;
}
.panel-head {
  display: flex; align-items: center; justify-content: space-between;
  font-family: var(--mono); font-size: 0.7rem; color: var(--muted);
  padding-bottom: 0.6rem; margin-bottom: 0.8rem;
  border-bottom: 1px solid var(--line-soft);
}

/* ---- 5. Controls -------------------------------------------------------
   The transition on transform is the whole trick. 90ms, 1px. You won't
   consciously see it; you'll feel the thing is well-built. */
.stButton > button {
  font-family: var(--mono);
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  border: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--text);
  border-radius: 4px;
  padding: 0.42rem 0.95rem;
  transition: background 90ms ease, border-color 90ms ease, transform 90ms ease;
}
.stButton > button:hover {
  background: #1F1F23;
  border-color: #33333A;
  transform: translateY(-1px);
}
.stButton > button:active { transform: translateY(0); }
.stButton > button[kind="primary"] {
  background: var(--signal);
  border-color: var(--signal);
  color: #0A0A0B;
  font-weight: 600;
}
.stButton > button[kind="primary"]:hover { background: #9BA2FF; border-color: #9BA2FF; }

.stTextArea textarea, .stTextInput input {
  font-family: var(--mono) !important;
  font-size: 0.84rem !important;
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
  color: var(--text) !important;
  line-height: 1.6 !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
  border-color: var(--signal) !important;
  box-shadow: 0 0 0 3px rgba(139,147,248,0.13) !important;
}
.stTextArea textarea::placeholder { color: var(--faint) !important; }

/* Visible keyboard focus everywhere, not just where it's pretty. */
*:focus-visible { outline: 2px solid var(--signal); outline-offset: 2px; }

/* ---- 6. Tabs as a segmented control, not underlined links ------------- */
[data-baseweb="tab-list"] {
  gap: 0; background: var(--surface); border: 1px solid var(--line);
  border-radius: 4px; padding: 3px; width: fit-content;
}
[data-baseweb="tab-list"] button {
  font-family: var(--mono) !important; font-size: 0.72rem !important;
  border-radius: 3px; padding: 0.3rem 0.85rem; color: var(--muted) !important;
}
[data-baseweb="tab-list"] button[aria-selected="true"] {
  background: var(--surface-2); color: var(--text) !important;
}
[data-baseweb="tab-highlight"], [data-baseweb="tab-border"] { display: none; }

/* ---- 7. Code wells ---------------------------------------------------- */
.stCode, pre {
  font-family: var(--mono) !important;
  font-size: 0.8rem !important;
  line-height: 1.65 !important;
  border: 1px solid var(--line) !important;
  border-radius: 4px !important;
}

/* ---- 8. Small parts --------------------------------------------------- */
.meta { font-family: var(--mono); font-size: 0.68rem; color: var(--faint); }
.rule { height: 1px; background: var(--line-soft); margin: 1.5rem 0; }
.chip {
  display: inline-block; font-family: var(--mono); font-size: 0.66rem;
  color: var(--muted); border: 1px solid var(--line); border-radius: 3px;
  padding: 0.12rem 0.45rem; margin-right: 0.3rem;
}
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }

/* Scrollbars are part of the design on a dark tool. */
::-webkit-scrollbar { width: 9px; height: 9px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #2A2A30; border-radius: 5px; }
::-webkit-scrollbar-thumb:hover { background: #3A3A42; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; }
  h1 { font-size: 1.3rem !important; }
}
</style>
"""


def inject() -> None:
    """Apply the CSS layer. Call once, right after set_page_config()."""
    st.markdown(CSS, unsafe_allow_html=True)
