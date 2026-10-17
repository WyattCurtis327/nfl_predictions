"""Chat — agent tools + Genie."""

from __future__ import annotations

import streamlit as st

from chat_engine import ChatEngine
from genie_client import metrics_space_id, rca_space_id
from theme import section_header

SAMPLE_PROMPTS = [
    "What are the highest-confidence picks this week?",
    "Why did we miss the spread in week 7?",
    "What are the most common root causes this season?",
    "Which teams have the best net defense lately?",
    "What was our ATS accuracy for the 2025 regular season?",
]


def _engine() -> ChatEngine:
    if "chat_engine" not in st.session_state:
        st.session_state.chat_engine = ChatEngine()
    return st.session_state.chat_engine


def _messages() -> list[dict[str, str]]:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    return st.session_state.chat_messages


section_header(
    "Chat",
    "Agent tools answer picks, RCA, and PBP questions deterministically. Genie handles open-ended accuracy SQL.",
)

metrics_id = metrics_space_id()
rca_id = rca_space_id()
status_cols = st.columns(3)
status_cols[0].caption(f"Metrics Genie: {'connected' if metrics_id else 'not linked'}")
status_cols[1].caption(f"RCA Genie: {'connected' if rca_id else 'not linked'}")
status_cols[2].caption("Tools: picks · RCA · causes · team ratings")

with st.sidebar:
    st.markdown("##### Chat")
    if st.button("New conversation", use_container_width=True):
        _engine().reset_genie()
        st.session_state.chat_messages = []
        st.rerun()
    st.markdown("**Sample prompts**")
    for index, prompt in enumerate(SAMPLE_PROMPTS):
        if st.button(prompt, use_container_width=True, key=f"sample_prompt_{index}"):
            st.session_state.pending_prompt = prompt

for message in _messages():
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("source"):
            st.caption(message["source"])

pending = st.session_state.pop("pending_prompt", None)
user_input = st.chat_input("Ask about picks, misses, team ratings, or accuracy…")
question = pending or user_input

if question:
    _messages().append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            try:
                answer, source = _engine().answer(question)
            except Exception as exc:  # noqa: BLE001
                answer = f"Something went wrong: {exc}"
                source = "error"
        st.markdown(answer)
        st.caption(source)
    _messages().append({"role": "assistant", "content": answer, "source": source})

if not _messages():
    st.info(
        "Start with a sample prompt in the sidebar, or ask a question below. "
        "Include **season**, **week**, or **AWAY @ HOME** when you can."
    )