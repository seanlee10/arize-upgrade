import pytest

from arize_upgrade.notify.base import Button, Notification
from arize_upgrade.notify.slack import SlackApiError, SlackNotifier, render_blocks

NOTIFICATION = Notification(
    title="Arize 11.43.0 available",
    fields={"Current": "11.41.0", "Target": "11.43.0"},
    body="* Storage classes are immutable.",
    buttons=(Button("Approve image push", "https://github.com/o/r/actions/runs/1"),),
    status="info",
)


def _blocks_of_type(blocks, kind):
    return [b for b in blocks if b["type"] == kind]


def test_title_is_rendered_as_a_header():
    header = _blocks_of_type(render_blocks(NOTIFICATION), "header")[0]
    assert "Arize 11.43.0 available" in header["text"]["text"]


def test_fields_are_rendered():
    rendered = str(render_blocks(NOTIFICATION))
    assert "Current" in rendered and "11.41.0" in rendered


def test_body_is_rendered():
    assert "Storage classes are immutable" in str(render_blocks(NOTIFICATION))


def test_buttons_become_link_buttons_with_urls():
    actions = _blocks_of_type(render_blocks(NOTIFICATION), "actions")[0]
    element = actions["elements"][0]
    assert element["type"] == "button"
    assert element["url"] == "https://github.com/o/r/actions/runs/1"
    assert element["text"]["text"] == "Approve image push"


def test_notification_without_buttons_has_no_actions_block():
    plain = Notification(title="t", fields={}, body=None, buttons=(), status="info")
    assert _blocks_of_type(render_blocks(plain), "actions") == []


def test_failure_status_is_visible_in_the_header():
    failed = Notification(title="Upgrade failed", fields={}, status="failure")
    assert "❌" in str(render_blocks(failed))


def test_success_status_is_visible_in_the_header():
    ok = Notification(title="Upgrade complete", fields={}, status="success")
    assert "✅" in str(render_blocks(ok))


def test_info_status_is_visible_in_the_header():
    info = Notification(title="Arize 11.43.0 available", fields={}, status="info")
    assert "\U0001f4e6" in str(render_blocks(info))


def test_send_posts_to_the_configured_channel():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(url=url, json=json, headers=headers)
        return {"ok": True, "ts": "1700000000.000100"}

    notifier = SlackNotifier(token="xoxb-x", channel="C123", post=fake_post)
    notifier.send(NOTIFICATION)

    assert captured["url"] == "https://slack.com/api/chat.postMessage"
    assert captured["json"]["channel"] == "C123"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-x"


def test_send_returns_the_thread_reference():
    notifier = SlackNotifier(
        token="x", channel="C1", post=lambda **kw: {"ok": True, "ts": "111.222"}
    )
    assert notifier.send(NOTIFICATION) == "111.222"


def test_reply_to_threads_the_message():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "333.444"}

    notifier = SlackNotifier(token="x", channel="C1", post=fake_post)
    notifier.send(NOTIFICATION, reply_to="111.222")
    assert captured["json"]["thread_ts"] == "111.222"


def test_no_thread_ts_key_when_not_replying():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "1"}

    SlackNotifier(token="x", channel="C1", post=fake_post).send(NOTIFICATION)
    assert "thread_ts" not in captured["json"]


def test_slack_api_error_is_raised():
    notifier = SlackNotifier(
        token="x",
        channel="C1",
        post=lambda **kw: {"ok": False, "error": "channel_not_found"},
    )
    with pytest.raises(SlackApiError, match="channel_not_found"):
        notifier.send(NOTIFICATION)


def test_fallback_text_is_set_for_notifications():
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured.update(json=json)
        return {"ok": True, "ts": "1"}

    SlackNotifier(token="x", channel="C1", post=fake_post).send(NOTIFICATION)
    assert captured["json"]["text"] == "Arize 11.43.0 available"
