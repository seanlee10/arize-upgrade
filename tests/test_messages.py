from datetime import date

from arize_upgrade import messages
from arize_upgrade.releases import Release
from arize_upgrade.versions import Version

CURRENT = Version(11, 41, 0)
TARGET = Version(11, 43, 0)
RUN_URL = "https://github.com/o/r/actions/runs/42"
NOTES = [
    Release(Version(11, 42, 0), date(2026, 8, 11), "Pin your storage classes.", None)
]


def test_detected_names_both_versions_in_fields():
    notification = messages.detected(CURRENT, TARGET, NOTES, RUN_URL)
    assert notification.fields["Currently deployed"] == "11.41.0"
    assert notification.fields["New version"] == "11.43.0"


def test_detected_title_carries_the_target_version():
    assert "11.43.0" in messages.detected(CURRENT, TARGET, NOTES, RUN_URL).title


def test_detected_includes_upgrade_notes_with_their_version():
    body = messages.detected(CURRENT, TARGET, NOTES, RUN_URL).body
    assert "11.42.0" in body
    assert "Pin your storage classes." in body


def test_detected_says_so_when_there_are_no_upgrade_notes():
    body = messages.detected(CURRENT, TARGET, [], RUN_URL).body
    assert "No upgrade notes" in body


def test_detected_button_points_at_the_run():
    button = messages.detected(CURRENT, TARGET, NOTES, RUN_URL).buttons[0]
    assert button.url == RUN_URL
    assert "image" in button.label.lower()


def test_images_pushed_names_the_registry():
    notification = messages.images_pushed(TARGET, "123.dkr.ecr.eu-west-1.amazonaws.com", RUN_URL)
    assert "123.dkr.ecr.eu-west-1.amazonaws.com" in notification.fields.values()


def test_images_pushed_restates_the_version_for_unthreaded_providers():
    notification = messages.images_pushed(TARGET, "reg", RUN_URL)
    assert "11.43.0" in notification.title or "11.43.0" in str(notification.fields)


def test_images_pushed_button_asks_for_install_approval():
    button = messages.images_pushed(TARGET, "reg", RUN_URL).buttons[0]
    assert button.url == RUN_URL
    assert "install" in button.label.lower()


def test_successful_result_is_marked_success():
    notification = messages.result(TARGET, True, "https://arize.example.com", RUN_URL)
    assert notification.status == "success"


def test_successful_result_offers_a_link_to_the_app():
    buttons = messages.result(TARGET, True, "https://arize.example.com", RUN_URL).buttons
    assert any(b.url == "https://arize.example.com" for b in buttons)


def test_failed_result_is_marked_failure():
    notification = messages.result(TARGET, False, "https://arize.example.com", RUN_URL)
    assert notification.status == "failure"


def test_failed_result_links_the_run_logs_and_not_the_app():
    notification = messages.result(TARGET, False, "https://arize.example.com", RUN_URL)
    urls = [b.url for b in notification.buttons]
    assert RUN_URL in urls
    assert "https://arize.example.com" not in urls


def test_alert_is_a_failure_with_the_detail_in_the_body():
    notification = messages.alert("Parser broke", "no headings found", RUN_URL)
    assert notification.status == "failure"
    assert "no headings found" in notification.body
    assert notification.buttons[0].url == RUN_URL
