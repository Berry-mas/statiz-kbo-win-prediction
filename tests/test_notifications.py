from __future__ import annotations

from unittest.mock import Mock, patch

from src.notifications import DiscordNotifier


def test_discord_notifier_skips_when_webhook_missing() -> None:
    notifier = DiscordNotifier(webhook_url=None)

    sent = notifier.send("Title", "Message", {"status": "ok"})

    assert sent is False


@patch("src.notifications.requests.post")
def test_discord_notifier_posts_message(mock_post: Mock) -> None:
    mock_response = Mock()
    mock_post.return_value = mock_response
    notifier = DiscordNotifier(webhook_url="https://discord.example/webhook")

    sent = notifier.send("Title", "Message", {"status": "ok"})

    assert sent is True
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["json"]["content"].startswith("**Title**")
    assert "`status`: `ok`" in kwargs["json"]["content"]
    mock_response.raise_for_status.assert_called_once()
