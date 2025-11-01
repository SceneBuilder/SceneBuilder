"""Base primitives for lint rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import ClassVar

from scene_builder.lint.context import LintContext, LintingOptions
from scene_builder.lint.models import LintIssue


class LintRule(ABC):
    """Abstract base class for lint rules."""

    code: ClassVar[str]
    description: ClassVar[str]

    @abstractmethod
    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        """Evaluate the rule against the linting context."""

    def __repr__(self) -> str:  # pragma: no cover - simple debug helper
        return f"{self.__class__.__name__}(code={self.code!r})"

