"""Thin wrapper around the Databricks Genie conversation API."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from typing import Any

from shared import env


def _workspace_client():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def _genie_space_from_app_resource(resource_name: str) -> str:
    app_name = env("DATABRICKS_APP_NAME")
    if not app_name:
        return ""
    client = _workspace_client()
    app = client.apps.get(app_name)
    for resource in app.resources or []:
        if resource.name == resource_name and resource.genie_space and resource.genie_space.space_id:
            return str(resource.genie_space.space_id).strip()
    return ""


@lru_cache(maxsize=1)
def _list_spaces_by_title() -> dict[str, str]:
    client = _workspace_client()
    titles: dict[str, str] = {}
    try:
        response = client.genie.list_spaces()
    except Exception:  # noqa: BLE001
        return titles
    for space in response.spaces or []:
        title = (space.title or "").strip()
        space_id = (space.space_id or space.id or "").strip()
        if title and space_id:
            titles[title.lower()] = space_id
    return titles


def resolve_space_id(*, resource_name: str, title: str, env_var: str) -> str:
    """Resolve a Genie space ID from env, app resource, or title lookup."""
    for candidate in (
        env(env_var),
        _genie_space_from_app_resource(resource_name),
        _list_spaces_by_title().get(title.lower()),
    ):
        if candidate:
            return candidate
    return ""


def metrics_space_id() -> str:
    return resolve_space_id(
        resource_name="genie-pick-metrics",
        title="NFL Pick Metrics",
        env_var="NFL_GENIE_METRICS_SPACE_ID",
    )


def rca_space_id() -> str:
    return resolve_space_id(
        resource_name="genie-pick-rca",
        title="NFL Pick Miss RCA",
        env_var="NFL_GENIE_RCA_SPACE_ID",
    )


def extract_message_text(message: Any) -> str:
    """Pull human-readable text from a completed Genie message."""
    chunks: list[str] = []
    for attachment in message.attachments or []:
        if attachment.text and attachment.text.content:
            chunks.append(attachment.text.content.strip())
        if attachment.query and attachment.query.query:
            chunks.append(f"```sql\n{attachment.query.query.strip()}\n```")
    if chunks:
        return "\n\n".join(chunks)
    if message.error and message.error.message:
        return f"Genie error: {message.error.message}"
    return "Genie returned an empty response. Try rephrasing or use a more specific week/matchup."


class GenieChat:
    """Stateful Genie conversation for one space."""

    def __init__(self, *, space_id: str) -> None:
        self.space_id = space_id
        self.conversation_id: str | None = None

    def ask(self, question: str) -> str:
        if not self.space_id:
            raise RuntimeError("Genie space ID is not configured.")
        client = _workspace_client()
        if self.conversation_id is None:
            message = client.genie.start_conversation_and_wait(
                space_id=self.space_id,
                content=question,
                timeout=timedelta(minutes=3),
            )
            self.conversation_id = message.conversation_id
            return extract_message_text(message)

        message = client.genie.create_message_and_wait(
            space_id=self.space_id,
            conversation_id=self.conversation_id,
            content=question,
            timeout=timedelta(minutes=3),
        )
        return extract_message_text(message)

    def reset(self) -> None:
        self.conversation_id = None