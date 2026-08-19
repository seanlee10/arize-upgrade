"""Build the Notification for each stage of the upgrade.

Every message restates the target version so it reads correctly on providers
without threading (Teams).
"""

from __future__ import annotations

from .notify.base import Button, Notification
from .releases import Release
from .versions import Version


def _format_notes(notes: list[Release]) -> str:
    if not notes:
        return "No upgrade notes between these versions."
    sections = [
        f"{release.version}\n{release.upgrade_notes}"
        for release in notes
        if release.upgrade_notes is not None
    ]
    if not sections:
        return "No upgrade notes between these versions."
    return "Upgrade notes\n\n" + "\n\n".join(sections)


def detected(
    current: Version, target: Version, notes: list[Release], run_url: str
) -> Notification:
    return Notification(
        title=f"Arize {target} is available",
        fields={
            "Currently deployed": str(current),
            "New version": str(target),
        },
        body=_format_notes(notes),
        buttons=(Button("Review and approve image push", run_url),),
        status="info",
    )


def images_pushed(target: Version, registry: str, run_url: str) -> Notification:
    return Notification(
        title=f"Arize {target} images are in ECR",
        fields={"Version": str(target), "Registry": registry},
        body="Images are pushed. Approve the install to upgrade the cluster.",
        buttons=(Button("Review and approve install", run_url),),
        status="info",
    )


def result(
    target: Version, succeeded: bool, app_url: str, run_url: str
) -> Notification:
    if succeeded:
        return Notification(
            title=f"Arize upgraded to {target}",
            fields={"Version": str(target), "Status": "Healthy"},
            body="All init jobs completed and every workload reported ready.",
            buttons=(
                Button("Open Arize", app_url),
                Button("View run", run_url),
            ),
            status="success",
        )
    return Notification(
        title=f"Arize upgrade to {target} FAILED",
        fields={"Version": str(target), "Status": "Failed"},
        body=(
            "The cluster may be partially upgraded. There is no automatic "
            "rollback. Check the run logs before retrying."
        ),
        buttons=(Button("View run logs", run_url),),
        status="failure",
    )


def alert(title: str, detail: str, run_url: str) -> Notification:
    return Notification(
        title=title,
        fields={},
        body=detail,
        buttons=(Button("View run logs", run_url),),
        status="failure",
    )
