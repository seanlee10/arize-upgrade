import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.teams import TeamsNotifier, TeamsWebhookError, render_card

NOTIFICATION = Notification(
    title="Arize 11.43.0 available",
    fields={"Current": "11.41.0", "Target": "11.43.0"},
    body="* Storage classes are immutable.",
    buttons=(Button("Approve image push", "https://github.com/o/r/actions/runs/1"),),
    status="info",
)


def _card(notification=NOTIFICATION):
    return render_card(notification)["attachments"][0]["content"]


def test_payload_uses_the_adaptive_card_attachment_envelope():
    payload = render_card(NOTIFICATION)
    attachment = payload["attachments"][0]
    assert payload["type"] == "message"
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"


def test_card_declares_a_supported_schema_version():
    assert _card()["version"] == "1.4"


def test_title_is_the_first_text_block():
    first = _card()["body"][0]
    assert first["type"] == "TextBlock"
    assert "Arize 11.43.0 available" in first["text"]


def test_fields_render_as_a_factset():
    factsets = [b for b in _card()["body"] if b["type"] == "FactSet"]
    facts = {f["title"]: f["value"] for f in factsets[0]["facts"]}
    assert facts == {"Current": "11.41.0", "Target": "11.43.0"}


def test_body_is_rendered():
    assert "Storage classes are immutable" in str(_card()["body"])


def test_buttons_become_openurl_actions():
    action = _card()["actions"][0]
    assert action["type"] == "Action.OpenUrl"
    assert action["title"] == "Approve image push"
    assert action["url"] == "https://github.com/o/r/actions/runs/1"


def test_notification_without_buttons_has_no_actions():
    plain = Notification(title="t", fields={}, buttons=())
    assert render_card(plain)["attachments"][0]["content"].get("actions", []) == []


def test_failure_status_is_visible():
    failed = Notification(title="Upgrade failed", status="failure")
    assert "❌" in str(render_card(failed))


def test_success_status_is_visible():
    ok = Notification(title="Upgrade complete", status="success")
    assert "✅" in str(render_card(ok))


def test_send_posts_to_the_webhook_url():
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(url=url, json=json)
        return 202

    TeamsNotifier(webhook_url="https://example.com/hook", post=fake_post).send(
        NOTIFICATION
    )
    assert captured["url"] == "https://example.com/hook"
    assert captured["json"]["type"] == "message"


def test_send_returns_none_because_teams_cannot_thread():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 202
    )
    assert notifier.send(NOTIFICATION) is None


def test_reply_to_is_accepted_and_ignored():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 200
    )
    assert notifier.send(NOTIFICATION, reply_to="111.222") is None


def test_non_2xx_response_raises():
    notifier = TeamsNotifier(
        webhook_url="https://example.com/hook", post=lambda **kw: 500
    )
    with pytest.raises(TeamsWebhookError, match="500"):
        notifier.send(NOTIFICATION)
