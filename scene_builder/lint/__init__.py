"""Linting utilities for validating generated room and scene layouts."""

from scene_builder.lint.context import (
    DEFAULT_RULES,
    LintContext,
    LintableObjectData,
    LintableRoomData,
    LintingOptions,
)
from scene_builder.lint.models import AABB, LintIssue, LintReport, LintSeverity
from scene_builder.lint.linter import lint_room, lint_scene
from scene_builder.lint.rules import LintRule

__all__ = [
    "LintIssue",
    "LintReport",
    "LintSeverity",
    "LintingOptions",
    "LintContext",
    "LintableObjectData",
    "LintableRoomData",
    "LintRule",
    "DEFAULT_RULES",
    "AABB",
    "lint_room",
    "lint_scene",
]
