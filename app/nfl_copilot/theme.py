"""Visual design system for the NFL Copilot Streamlit app."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg-deep: #0b0f14;
  --bg-panel: #121a24;
  --bg-elevated: #1a2433;
  --border: #2a3648;
  --text: #e8edf4;
  --text-muted: #8b9bb4;
  --accent: #2dd4a8;
  --accent-dim: #1a9e7a;
  --warn: #f5b942;
  --danger: #f07178;
  --spread: #5b9cf5;
  --total: #c084fc;
  --radius: 12px;
}

.stApp {
  background: radial-gradient(ellipse 120% 80% at 10% -20%, #1a2a3d 0%, var(--bg-deep) 55%);
  color: var(--text);
  font-family: "DM Sans", system-ui, sans-serif;
}

.block-container { padding-top: 1.25rem; max-width: 1280px; }

h1, h2, h3, h4, h5, h6, p, label, span {
  font-family: "DM Sans", system-ui, sans-serif;
}

code, .stCode, pre {
  font-family: "JetBrains Mono", ui-monospace, monospace !important;
}

div[data-testid="stMetric"] {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.85rem 1rem;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.25);
}

div[data-testid="stMetric"] label {
  color: var(--text-muted) !important;
  font-size: 0.78rem !important;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

div[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: var(--text) !important;
  font-weight: 700 !important;
}

section[data-testid="stSidebar"] {
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
}

section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stSlider label,
section[data-testid="stSidebar"] .stMultiSelect label {
  color: var(--text-muted) !important;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.35rem;
  background: transparent;
  border-bottom: 1px solid var(--border);
}

.stTabs [data-baseweb="tab"] {
  background: transparent;
  border-radius: 8px 8px 0 0;
  color: var(--text-muted);
  font-weight: 600;
  padding: 0.5rem 1rem;
}

.stTabs [aria-selected="true"] {
  background: var(--bg-elevated) !important;
  color: var(--accent) !important;
  border: 1px solid var(--border);
  border-bottom-color: var(--bg-elevated) !important;
}

div[data-testid="stDataFrame"] {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.copilot-brand {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 1.5rem;
  padding: 1.1rem 1.25rem;
  background: linear-gradient(135deg, var(--bg-panel) 0%, var(--bg-elevated) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
}

.copilot-brand-icon {
  font-size: 2rem;
  line-height: 1;
}

.copilot-brand-title {
  margin: 0;
  font-size: 1.55rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text);
}

.copilot-brand-sub {
  margin: 0.15rem 0 0;
  color: var(--text-muted);
  font-size: 0.92rem;
}

.copilot-section {
  margin: 1.5rem 0 0.75rem;
}

.copilot-section h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text);
}

.copilot-section p {
  margin: 0.35rem 0 0;
  color: var(--text-muted);
  font-size: 0.92rem;
}

.pick-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.1rem;
  margin-bottom: 0.75rem;
  transition: border-color 0.15s ease;
}

.pick-card:hover { border-color: var(--accent-dim); }

.pick-card.hot {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px rgba(45, 212, 168, 0.15);
}

.pick-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}

.pick-matchup {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
}

.pick-meta {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-top: 0.2rem;
}

.pick-badges { display: flex; flex-wrap: wrap; gap: 0.4rem; justify-content: flex-end; }

.badge {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.badge-spread { background: rgba(91, 156, 245, 0.18); color: #8ec0ff; border: 1px solid rgba(91, 156, 245, 0.35); }
.badge-total { background: rgba(192, 132, 252, 0.18); color: #d8b4fe; border: 1px solid rgba(192, 132, 252, 0.35); }
.badge-hot { background: rgba(45, 212, 168, 0.18); color: var(--accent); border: 1px solid rgba(45, 212, 168, 0.4); }
.badge-muted { background: var(--bg-elevated); color: var(--text-muted); border: 1px solid var(--border); }

.pick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.pick-leg {
  background: var(--bg-elevated);
  border-radius: 10px;
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--border);
}

.pick-leg-label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 0.35rem;
}

.pick-leg-value {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--text);
}

.pick-leg-detail {
  font-size: 0.82rem;
  color: var(--text-muted);
  margin-top: 0.25rem;
}

.rca-narrative {
  background: rgba(45, 212, 168, 0.08);
  border: 1px solid rgba(45, 212, 168, 0.25);
  border-radius: var(--radius);
  padding: 0.9rem 1rem;
  color: var(--text);
  font-size: 0.92rem;
  line-height: 1.55;
  white-space: pre-wrap;
}

.home-tile {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.1rem 1.2rem;
  height: 100%;
}

.home-tile h3 {
  margin: 0 0 0.5rem;
  font-size: 1.05rem;
  color: var(--text);
}

.home-tile p {
  margin: 0;
  font-size: 0.88rem;
  color: var(--text-muted);
  line-height: 1.5;
}

.agent-slot {
  background: linear-gradient(135deg, #141e2b 0%, #1a2838 100%);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 1rem 1.1rem;
  color: var(--text-muted);
  font-size: 0.88rem;
}

.agent-slot strong { color: var(--accent); }

div[data-testid="stChatMessage"] {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

@media (max-width: 768px) {
  .pick-grid { grid-template-columns: 1fr; }
}
</style>
"""


def inject_theme() -> None:
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def render_brand(*, subtitle: str | None = None) -> None:
    text = subtitle or "Predictions, play-by-play, and root-cause analysis in one workspace."
    st.markdown(
        f"""
        <div class="copilot-brand">
          <div class="copilot-brand-icon">🏈</div>
          <div>
            <p class="copilot-brand-title">NFL Copilot</p>
            <p class="copilot-brand-sub">{html.escape(text)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_header(title: str, subtitle: str = "") -> None:
    sub_html = f"<p>{html.escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f'<div class="copilot-section"><h2>{html.escape(title)}</h2>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def confidence_badge(label: str, pick: str | None, confidence: float | None, *, hot: bool) -> str:
    if not pick or (isinstance(confidence, float) and pd.isna(confidence)):
        return f'<span class="badge badge-muted">{html.escape(label)} —</span>'
    conf_text = f"{confidence:.0%}" if confidence is not None and not pd.isna(confidence) else ""
    css = "badge-hot" if hot else ("badge-spread" if label == "Spread" else "badge-total")
    return (
        f'<span class="badge {css}">{html.escape(label)} {html.escape(str(pick))} '
        f'{html.escape(conf_text)}</span>'
    )


def render_pick_card(
    row: pd.Series,
    *,
    min_confidence: float,
    format_line,
) -> None:
    spread_hot = (
        pd.notna(row.get("spread_confidence"))
        and float(row["spread_confidence"]) >= min_confidence
    )
    total_hot = (
        pd.notna(row.get("total_confidence"))
        and float(row["total_confidence"]) >= min_confidence
    )
    hot = spread_hot or total_hot
    card_class = "pick-card hot" if hot else "pick-card"
    away = html.escape(str(row["away_abbr"]))
    home = html.escape(str(row["home_abbr"]))
    gameday = html.escape(str(row.get("gameday", "")))
    kickoff = html.escape(str(row.get("kickoff_et", "")))

    spread_pick = row.get("spread_pick")
    spread_conf = row.get("spread_confidence")
    total_pick = row.get("total_pick")
    total_conf = row.get("total_confidence")

    badges = "".join(
        [
            confidence_badge("Spread", str(spread_pick) if spread_pick else None, spread_conf, hot=spread_hot),
            confidence_badge("Total", str(total_pick) if total_pick else None, total_conf, hot=total_hot),
        ]
    )
    if hot:
        badges += '<span class="badge badge-hot">High conviction</span>'

    spread_detail = (
        f"Line {format_line(row.get('away_spread'))} · "
        f"Proj {row.get('proj_away_score', '—')}–{row.get('proj_home_score', '—')}"
    )
    total_detail = (
        f"Line {format_line(row.get('total_line'))} · "
        f"Proj {format_line(row.get('proj_total'))}"
    )

    st.markdown(
        f"""
        <div class="{card_class}">
          <div class="pick-card-header">
            <div>
              <div class="pick-matchup">{away} @ {home}</div>
              <div class="pick-meta">{gameday} · {kickoff} ET</div>
            </div>
            <div class="pick-badges">{badges}</div>
          </div>
          <div class="pick-grid">
            <div class="pick-leg">
              <div class="pick-leg-label">Spread</div>
              <div class="pick-leg-value">{html.escape(str(spread_pick or '—'))}</div>
              <div class="pick-leg-detail">{html.escape(spread_detail)}</div>
            </div>
            <div class="pick-leg">
              <div class="pick-leg-label">Total</div>
              <div class="pick-leg-value">{html.escape(str(total_pick or '—'))}</div>
              <div class="pick-leg-detail">{html.escape(total_detail)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_narrative(text: str) -> None:
    st.markdown(f'<div class="rca-narrative">{html.escape(text)}</div>', unsafe_allow_html=True)


def render_agent_slot() -> None:
    st.markdown(
        """
        <div class="agent-slot">
          <strong>Agent tools (coming next)</strong> — Chat will call deterministic helpers
          like <code>explain_miss</code> and <code>team_pbp_ratings</code> on top of Genie
          for open-ended accuracy questions.
        </div>
        """,
        unsafe_allow_html=True,
    )