import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.slack import render_blocks
from arize_upgrade.notify.slack_webhook import SlackWebhookError, SlackWebhookNotifier

NOTIFICATION = Notification(
    title="Arize 11.43.0 available",
    fields={"Current": "11.41.0", "Target": "11.43.0"},
    body="* Storage classes are immutable.",
    buttons=(Button("Approve image push", "https://github.com/o/r/actions/runs/1"),),
    status="info",
)


def test_payload_carries_text_and_blocks():
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json=json)
        return 200

    SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx", post=fake_post
    ).send(NOTIFICATION)

    assert captured["json"]["text"] == "Arize 11.43.0 available"
    assert "blocks" in captured["json"]


def test_blocks_are_exactly_what_render_blocks_produces():
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json=json)
        return 200

    SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx", post=fake_post
    ).send(NOTIFICATION)

    assert captured["json"]["blocks"] == render_blocks(NOTIFICATION)


def test_send_posts_to_the_configured_webhook_url():
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url)
        return 200

    SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx", post=fake_post
    ).send(NOTIFICATION)

    assert captured["url"] == "https://hooks.slack.com/services/T000/B000/xxxx"


def test_send_returns_none_because_incoming_webhooks_cannot_thread():
    notifier = SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx",
        post=lambda **kw: 200,
    )
    assert notifier.send(NOTIFICATION) is None


def test_reply_to_is_accepted_and_ignored():
    notifier = SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx",
        post=lambda **kw: 200,
    )
    assert notifier.send(NOTIFICATION, reply_to="111.222") is None


def test_non_2xx_response_raises():
    notifier = SlackWebhookNotifier(
        webhook_url="https://hooks.slack.com/services/T000/B000/xxxx",
        post=lambda **kw: 500,
    )
    with pytest.raises(SlackWebhookError, match="500"):
        notifier.send(NOTIFICATION)
