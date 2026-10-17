"""Deterministic agent tools backed by Unity Catalog SQL."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from queries import (
    cause_summary_sql,
    format_narrative,
    latest_picks_sql,
    missed_picks_sql,
)
from shared import (
    DEFAULT_SEASON,
    pick_miss_rca_view,
    pbp_table,
    predictions_table,
    sql_query,
    table_has_column,
)
from team_ratings_queries import add_net_ratings, team_scoring_sql

RCA_VIEW = pick_miss_rca_view()
PREDICTIONS_TABLE = predictions_table()

_WEEK_RE = re.compile(r"\bweek\s*(\d{1,2})\b", re.I)
_SEASON_RE = re.compile(r"\b(?:season\s*)?(20\d{2})\b")
_MATCHUP_RE = re.compile(r"\b([A-Z]{2,3})\s*(?:@|vs\.?|versus)\s*([A-Z]{2,3})\b", re.I)


def _parse_week(text: str, default: int | None = None) -> int | None:
    match = _WEEK_RE.search(text)
    if match:
        return int(match.group(1))
    return default


def _parse_season(text: str) -> int:
    match = _SEASON_RE.search(text)
    return int(match.group(1)) if match else DEFAULT_SEASON


def _parse_matchup(text: str) -> tuple[str, str] | None:
    match = _MATCHUP_RE.search(text.upper())
    if not match:
        return None
    return match.group(1).upper(), match.group(2).upper()


def _format_pick_lines(frame: pd.DataFrame, *, limit: int = 8) -> str:
    if frame.empty:
        return "No picks matched that question."
    lines: list[str] = []
    for _, row in frame.head(limit).iterrows():
        spread = row.get("spread_pick") or "—"
        total = row.get("total_pick") or "—"
        spread_conf = row.get("spread_confidence")
        total_conf = row.get("total_confidence")
        spread_pct = f"{spread_conf:.0%}" if pd.notna(spread_conf) else "—"
        total_pct = f"{total_conf:.0%}" if pd.notna(total_conf) else "—"
        lines.append(
            f"- {row['away_abbr']} @ {row['home_abbr']}: spread **{spread}** ({spread_pct}), "
            f"total **{total}** ({total_pct})"
        )
    if len(frame) > limit:
        lines.append(f"- …and {len(frame) - limit} more games.")
    return "\n".join(lines)


class AgentTools:
    """SQL-backed tools the chat router can call directly."""

    def summarize_miss_causes(self, question: str) -> str:
        season = _parse_season(question)
        frame = sql_query(cause_summary_sql(RCA_VIEW, season=season))
        if frame.empty:
            return f"No RCA misses found for season {season}."
        lines = [f"Top miss causes — season {season}:"]
        for _, row in frame.head(8).iterrows():
            lines.append(f"- {row['primary_cause']}: {int(row['misses'])} misses")
        return "\n".join(lines)

    def explain_miss(self, question: str) -> str | None:
        season = _parse_season(question)
        week = _parse_week(question)
        matchup = _parse_matchup(question)
        misses = sql_query(missed_picks_sql(RCA_VIEW, season=season, week=week))
        if misses.empty:
            return f"No RCA misses for season {season}" + (f", week {week}" if week else "") + "."

        if matchup:
            away, home = matchup
            hits = misses[
                (misses["away_abbr"].astype(str).str.upper() == away)
                & (misses["home_abbr"].astype(str).str.upper() == home)
            ]
            if hits.empty:
                return f"No miss RCA for {away} @ {home} in season {season}" + (
                    f", week {week}" if week else ""
                ) + "."
            return format_narrative(hits.iloc[0].to_dict())

        if week is not None:
            week_misses = misses[misses["week"] == week]
            if week_misses.empty:
                return f"No misses recorded for season {season}, week {week}."
            lines = [f"Misses for season {season}, week {week} ({len(week_misses)} games):"]
            for _, row in week_misses.iterrows():
                lines.append(
                    f"- {row['away_abbr']} @ {row['home_abbr']}: {row['miss_types']} "
                    f"(`{row['primary_cause']}`)"
                )
            return "\n".join(lines)

        return None

    def weekly_picks(self, question: str) -> str:
        season = _parse_season(question)
        season_weeks = sql_query(
            f"""
            SELECT week, COUNT(*) AS games
            FROM {PREDICTIONS_TABLE}
            WHERE season = {season}
            GROUP BY week
            ORDER BY week DESC
            LIMIT 1
            """
        )
        if season_weeks.empty:
            return f"No predictions found for season {season}."
        week = _parse_week(question) or int(season_weeks["week"].iloc[0])
        has_model_id = table_has_column(PREDICTIONS_TABLE, "model_id")
        picks = sql_query(
            latest_picks_sql(
                PREDICTIONS_TABLE,
                season=season,
                week=week,
                has_model_id=has_model_id,
            )
        )
        if picks.empty:
            return f"No picks for season {season}, week {week}."

        if re.search(r"\b(high|top|best|confidence|conviction)\b", question, re.I):
            threshold = 0.55
            hot = picks[
                (picks["spread_confidence"] >= threshold) | (picks["total_confidence"] >= threshold)
            ].sort_values(
                ["spread_confidence", "total_confidence"],
                ascending=False,
            )
            header = f"High-confidence picks — season {season}, week {week}:"
            return header + "\n" + _format_pick_lines(hot)

        return f"Monte Carlo picks — season {season}, week {week}:\n" + _format_pick_lines(picks)

    def team_ratings_summary(self, question: str) -> str:
        season = _parse_season(question)
        week = _parse_week(question)
        weeks_sql = f"""
            SELECT DISTINCT week
            FROM {pbp_table()}
            WHERE season = {season} AND season_type IN ('REG','WC','DIV','CON','SB')
            ORDER BY week
        """
        try:
            weeks_frame = sql_query(weeks_sql)
        except Exception:  # noqa: BLE001
            return "Could not load play-by-play weeks for team ratings."

        if weeks_frame.empty:
            return f"No play-by-play data for season {season}."

        weeks = weeks_frame["week"].astype(int).tolist()
        if week is not None:
            window = [week]
        else:
            window = weeks[-4:] if len(weeks) >= 4 else weeks

        ratings = add_net_ratings(
            sql_query(team_scoring_sql(pbp_table(), season=season, weeks=window))
        )
        if ratings.empty:
            return "No team ratings for that window."

        offense = ratings.sort_values("net_offensive", ascending=False).head(5)
        defense = ratings.sort_values("net_defensive", ascending=False).head(5)
        week_label = ", ".join(str(value) for value in window)
        lines = [f"Team ratings — season {season}, weeks {week_label}:"]
        lines.append("**Top net offense**")
        for _, row in offense.iterrows():
            lines.append(f"- {row['team']}: {row['net_offensive']:+.1f}")
        lines.append("**Top net defense**")
        for _, row in defense.iterrows():
            lines.append(f"- {row['team']}: {row['net_defensive']:+.1f}")
        return "\n".join(lines)

    def help_text(self) -> str:
        return (
            "I can answer using **agent tools** (fast, deterministic) or **Genie** (open-ended SQL).\n\n"
            "**Try:**\n"
            "- `What are the picks for week 7?`\n"
            "- `Why did we miss the SF @ KC spread in week 5?`\n"
            "- `Most common root causes this season`\n"
            "- `Which teams have the best net defense over the last 4 weeks?`\n"
            "- `What was our ATS accuracy for the 2025 regular season?` (Genie)\n\n"
            "Include a **season**, **week**, or **AWAY @ HOME** matchup when you can."
        )