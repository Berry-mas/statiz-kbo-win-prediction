"""
Discord notifications for unattended scheduler runs.

The notifier is intentionally optional: if DISCORD_WEBHOOK_URL is not set,
messages are logged and skipped so local tests and dry runs do not need secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger


@dataclass(frozen=True)
class DiscordNotifier:
    """Send compact event messages to a Discord webhook."""

    webhook_url: str | None = None
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> DiscordNotifier:
        """Build a notifier from environment variables."""
        return cls(webhook_url=os.getenv("DISCORD_WEBHOOK_URL"))

    def send(
        self,
        title: str,
        message: str,
        fields: dict[str, Any] | None = None,
    ) -> bool:
        """Send a Discord webhook message.

        Args:
            title: Short event title.
            message: Human-readable event body.
            fields: Optional structured values rendered below the message.

        Returns:
            True if a webhook request was sent successfully; False otherwise.
        """
        if not self.webhook_url:
            logger.info(
                "Discord webhook not configured; skipping notification: {}", title
            )
            return False

        content = self._format_message(title, message, fields or {})
        response = requests.post(
            self.webhook_url,
            json={"content": content},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return True

    @staticmethod
    def _format_message(title: str, message: str, fields: dict[str, Any]) -> str:
        """Return Discord markdown for a scheduler event."""
        lines = [f"**{title}**", message]
        for key, value in fields.items():
            lines.append(f"- `{key}`: `{value}`")
        return "\n".join(lines)
