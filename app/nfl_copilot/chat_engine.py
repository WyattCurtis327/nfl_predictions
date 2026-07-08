"""Route chat questions to agent tools or Genie."""

from __future__ import annotations

import re

from agent_tools import AgentTools
from genie_client import GenieChat, metrics_space_id, rca_space_id

_METRICS_PATTERNS = (
    r"\b(ats|accuracy|hit rate|over/under|o/u|graded|wins?|losses?)\b",
    r"\bgame_pick_metrics\b",
)
_RCA_PATTERNS = (
    r"\b(why|miss|missed|root cause|rca|explain)\b",
    r"\bpick_miss_rca\b",
)
_PICKS_PATTERNS = (r"\b(pick|spread|total|line|confidence|monte carlo)\b",)
_RATINGS_PATTERNS = (r"\b(team rating|net offensive|net defensive|pbp|play[- ]by[- ]play)\b",)
_CAUSE_PATTERNS = (r"\b(common|top|most|frequent).*(cause|reason)\b", r"\broot causes?\b",)


def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _select_genie_space(question: str) -> tuple[str, str]:
    if _matches(_RCA_PATTERNS, question) and not _matches(_METRICS_PATTERNS, question):
        space_id = rca_space_id()
        if space_id:
            return space_id, "Genie · NFL Pick Miss RCA"
    space_id = metrics_space_id() or rca_space_id()
    label = "Genie · NFL Pick Metrics" if space_id == metrics_space_id() else "Genie · NFL Pick Miss RCA"
    return space_id, label


class ChatEngine:
    def __init__(self) -> None:
        self.tools = AgentTools()
        self._genie_sessions: dict[str, GenieChat] = {}

    def reset_genie(self) -> None:
        self._genie_sessions.clear()

    def _genie_for_space(self, space_id: str) -> GenieChat:
        if space_id not in self._genie_sessions:
            self._genie_sessions[space_id] = GenieChat(space_id=space_id)
        return self._genie_sessions[space_id]

    def answer(self, question: str) -> tuple[str, str]:
        text = question.strip()
        if not text:
            return "Ask a question about picks, misses, team ratings, or accuracy.", "help"

        lowered = text.lower()
        if lowered in {"help", "?", "commands"}:
            return self.tools.help_text(), "agent tool · help"

        if _matches(_CAUSE_PATTERNS, lowered):
            return self.tools.summarize_miss_causes(text), "agent tool · summarize_causes"

        if _matches(_RCA_PATTERNS, lowered):
            explained = self.tools.explain_miss(text)
            if explained:
                return explained, "agent tool · explain_miss"

        if _matches(_PICKS_PATTERNS, lowered):
            return self.tools.weekly_picks(text), "agent tool · weekly_picks"

        if _matches(_RATINGS_PATTERNS, lowered):
            return self.tools.team_ratings_summary(text), "agent tool · team_ratings"

        space_id, label = _select_genie_space(text)
        if space_id:
            try:
                reply = self._genie_for_space(space_id).ask(text)
                return reply, label
            except Exception as exc:  # noqa: BLE001
                fallback = self.tools.explain_miss(text)
                if fallback:
                    return (
                        f"{fallback}\n\n_(Genie unavailable: {exc})_",
                        "agent tool · explain_miss",
                    )
                return (
                    f"Genie is unavailable ({exc}). Try a picks/RCA question with season, week, "
                    f"or matchup — e.g. `picks for week 7` or `why did we miss KC @ BUF week 5`.",
                    "error",
                )

        picks = self.tools.weekly_picks(text)
        if "No predictions" not in picks and "No picks" not in picks:
            return picks, "agent tool · weekly_picks"
        return self.tools.help_text(), "agent tool · help"