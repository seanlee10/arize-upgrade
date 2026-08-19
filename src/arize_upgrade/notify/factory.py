"""Select exactly one notification provider from the environment."""

from __future__ import annotations

from typing import Mapping

from .base import Notifier


class UnknownProvider(ValueError):
    """Raised when NOTIFY_PROVIDER is unset or not recognised."""


class MissingProviderConfig(ValueError):
    """Raised when the selected provider's secrets are absent."""


def build_notifier(env: Mapping[str, str]) -> Notifier:
    provider = env.get("NOTIFY_PROVIDER", "").strip().lower()

    if provider == "slack":
        from .slack import SlackNotifier

        token = env.get("SLACK_BOT_TOKEN")
        channel = env.get("SLACK_CHANNEL_ID")
        if not token or not channel:
            raise MissingProviderConfig(
                "NOTIFY_PROVIDER=slack requires SLACK_BOT_TOKEN and SLACK_CHANNEL_ID"
            )
        return SlackNotifier(token=token, channel=channel)

    if provider == "teams":
        from .teams import TeamsNotifier

        webhook = env.get("TEAMS_WEBHOOK_URL")
        if not webhook:
            raise MissingProviderConfig(
                "NOTIFY_PROVIDER=teams requires TEAMS_WEBHOOK_URL"
            )
        return TeamsNotifier(webhook_url=webhook)

    raise UnknownProvider(
        f"NOTIFY_PROVIDER must be 'slack' or 'teams', got {provider!r}"
    )
