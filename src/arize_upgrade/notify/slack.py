"""Slack notifier: Block Kit rendering over chat.postMessage."""

from __future__ import annotations

from typing import Any, Callable

from .base import Notification, Status

POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

_STATUS_ICON: dict[Status, str] = {
    "info": "\U0001f4e6",  # package
    "success": "✅",  # check mark
    "failure": "❌",  # cross mark
}


class SlackApiError(RuntimeError):
    """Raised when Slack responds with ok=false."""


def render_blocks(notification: Notification) -> list[dict[str, Any]]:
    icon = _STATUS_ICON[notification.status]
    # Only prepend icon for outcome statuses (success/failure), not info
    title_text = notification.title
    if notification.status != "info":
        title_text = f"{icon} {title_text}"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": title_text[:150],
                "emoji": True,
            },
        }
    ]

    if notification.fields:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*{key}*\n{value}"}
                    for key, value in notification.fields.items()
                ],
            }
        )

    if notification.body:
        # Slack rejects text blocks over 3000 characters.
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": notification.body[:2900]},
            }
        )

    if notification.buttons:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": button.label,
                            "emoji": True,
                        },
                        "url": button.url,
                    }
                    for button in notification.buttons
                ],
            }
        )

    return blocks


def _default_post(url: str, json: dict, headers: dict, timeout: float) -> dict:
    import requests

    response = requests.post(url, json=json, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


class SlackNotifier:
    """Posts to Slack, threading every message under the first one."""

    def __init__(
        self,
        token: str,
        channel: str,
        *,
        post: Callable[..., dict] | None = None,
    ) -> None:
        self._token = token
        self._channel = channel
        self._post = post or _default_post

    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        payload: dict[str, Any] = {
            "channel": self._channel,
            # Fallback text for notifications and accessibility.
            "text": notification.title,
            "blocks": render_blocks(notification),
        }
        if reply_to:
            payload["thread_ts"] = reply_to

        body = self._post(
            url=POST_MESSAGE_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            timeout=30,
        )
        if not body.get("ok"):
            raise SlackApiError(f"chat.postMessage failed: {body.get('error')}")
        return body.get("ts")
