"""Semantic version parsing and comparison for Arize releases."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class InvalidVersion(ValueError):
    """Raised when a string is not a bare X.Y.Z version."""


@dataclass(frozen=True, order=True)
class Version:
    """An Arize release version.

    ``order=True`` compares by field declaration order, which gives correct
    numeric semver ordering: 11.9.0 < 11.40.0.
    """

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> "Version":
        match = _PATTERN.match(text.strip())
        if match is None:
            raise InvalidVersion(f"not a valid X.Y.Z version: {text!r}")
        return cls(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
