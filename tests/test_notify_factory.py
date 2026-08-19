import dataclasses

import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.factory import (
    MissingProviderConfig,
    UnknownProvider,
    build_notifier,
)
from arize_upgrade.notify.slack import SlackNotifier
from arize_upgrade.notify.teams import TeamsNotifier


def test_builds_slack_notifier():
    notifier = build_notifier(
        {
            "NOTIFY_PROVIDER": "slack",
            "SLACK_BOT_TOKEN": "xoxb-test",
            "SLACK_CHANNEL_ID": "C123",
        }
    )
    assert isinstance(notifier, SlackNotifier)


def test_builds_teams_notifier():
    notifier = build_notifier(
        {
            "NOTIFY_PROVIDER": "teams",
            "TEAMS_WEBHOOK_URL": "https://example.com/hook",
        }
    )
    assert isinstance(notifier, TeamsNotifier)


def test_provider_is_case_insensitive():
    notifier = build_notifier(
        {"NOTIFY_PROVIDER": "SLACK", "SLACK_BOT_TOKEN": "x", "SLACK_CHANNEL_ID": "C1"}
    )
    assert isinstance(notifier, SlackNotifier)


def test_unknown_provider_raises_rather_than_silently_skipping():
    with pytest.raises(UnknownProvider):
        build_notifier({"NOTIFY_PROVIDER": "discord"})


def test_missing_provider_raises():
    with pytest.raises(UnknownProvider):
        build_notifier({})


def test_slack_without_token_raises():
    with pytest.raises(MissingProviderConfig):
        build_notifier({"NOTIFY_PROVIDER": "slack", "SLACK_CHANNEL_ID": "C1"})


def test_teams_without_webhook_raises():
    with pytest.raises(MissingProviderConfig):
        build_notifier({"NOTIFY_PROVIDER": "teams"})


def test_notification_is_frozen():
    notification = Notification(
        title="t",
        fields={},
        body=None,
        buttons=(Button("Open", "https://example.com"),),
        status="info",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        notification.title = "other"  # type: ignore[misc]


def test_notification_is_not_hashable_because_fields_is_a_dict():
    notification = Notification(title="t", fields={}, status="info")
    with pytest.raises(TypeError):
        hash(notification)
