"""Microsoft Teams notifier: Adaptive Card over a Power Automate webhook.

Teams incoming webhooks cannot thread, so ``send`` returns None and every card
restates the version and carries the run link, making it readable alone.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import Notification, Status

_STATUS_ICON: dict[Status, str] = {
    "info": "\U0001f4e6",  # package
    "success": "✅",  # check mark
    "failure": "❌",  # cross mark
}


class TeamsWebhookError(RuntimeError):
    """Raised when the Teams webhook returns a non-2xx status."""


def render_card(notification: Notification) -> dict[str, Any]:
    icon = _STATUS_ICON[notification.status]
    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"{icon} {notification.title}",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        }
    ]

    if notification.fields:
        body.append(
            {
                "type": "FactSet",
                "facts": [
                    {"title": key, "value": value}
                    for key, value in notification.fields.items()
                ],
            }
        )

    if notification.body:
        body.append({"type": "TextBlock", "text": notification.body, "wrap": True})

    card: dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
        "actions": [
            {"type": "Action.OpenUrl", "title": button.label, "url": button.url}
            for button in notification.buttons
        ],
    }

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def _default_post(url: str, json: dict, timeout: float) -> int:
    import requests

    return requests.post(url, json=json, timeout=timeout).status_code


class TeamsNotifier:
    def __init__(
        self,
        webhook_url: str,
        *,
        post: Callable[..., int] | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._post = post or _default_post

    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        # reply_to is accepted for interface compatibility and ignored:
        # Teams incoming webhooks have no threading model.
        status = self._post(
            url=self._webhook_url, json=render_card(notification), timeout=30
        )
        if not 200 <= status < 300:
            raise TeamsWebhookError(f"Teams webhook returned HTTP {status}")
        return None
