"""Slack notifier: Block Kit rendering over an incoming webhook.

Unlike ``slack.py``'s bot-token/``chat.postMessage`` path, this needs only
the ``incoming-webhook`` scope — no ``chat:write``, no channel invite, no
``SLACK_CHANNEL_ID`` (the channel is fixed at webhook creation). The
tradeoff is threading: incoming webhooks return no ``ts``, so ``send``
always returns None and every message arrives as its own separate post,
the same limitation ``teams.py`` has.

Block Kit rendering is shared with ``slack.py`` via ``render_blocks`` so the
two Slack providers cannot drift apart.
"""

from __future__ import annotations

from typing import Any, Callable

from .base import Notification
from .slack import render_blocks


class SlackWebhookError(RuntimeError):
    """Raised when the Slack incoming webhook returns a non-2xx status."""


def _default_post(url: str, json: dict, timeout: float) -> int:
    import requests

    return requests.post(url, json=json, timeout=timeout).status_code


class SlackWebhookNotifier:
    """Posts to a Slack incoming webhook. Cannot thread."""

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
        # Slack incoming webhooks have no threading model.
        payload: dict[str, Any] = {
            # Fallback text for notifications and accessibility.
            "text": notification.title,
            "blocks": render_blocks(notification),
        }
        status = self._post(url=self._webhook_url, json=payload, timeout=30)
        if not 200 <= status < 300:
            raise SlackWebhookError(f"Slack webhook returned HTTP {status}")
        return None
