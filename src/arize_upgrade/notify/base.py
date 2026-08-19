"""Provider-agnostic notification types.

A Notification is built once from domain objects and rendered per provider.
Callers never branch on which provider is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

Status = Literal["info", "success", "failure"]


@dataclass(frozen=True)
class Button:
    """A link button. Both Slack and Teams render these as real buttons."""

    label: str
    url: str


@dataclass(frozen=True)
class Notification:
    """A provider-agnostic notification.

    Frozen, but deliberately NOT hashable: `fields` is a dict, so `hash()`
    raises. Nothing needs a Notification as a dict key; keeping `fields` a
    plain dict is what makes every call site readable.
    """

    title: str
    fields: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    buttons: tuple[Button, ...] = ()
    status: Status = "info"


class Notifier(Protocol):
    def send(
        self, notification: Notification, reply_to: str | None = None
    ) -> str | None:
        """Post a notification.

        Returns a thread reference if the provider supports threading,
        otherwise None. Callers must treat the return value as optional.
        """
        ...
