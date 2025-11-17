"""Linting utilities for validating generated room and scene layouts."""

from scene_builder.validation.context import (
    DEFAULT_RULES,
    LintContext,
    LintableObjectData,
    LintableRoomData,
    LintingOptions,
)
from scene_builder.validation.resolver import IssueResolutionOutput, IssueResolver
from scene_builder.validation.models import AABB, LintIssue, LintReport, LintSeverity
from scene_builder.validation.tracker import IssueTracker
from scene_builder.validation.linter import (
    format_lint_feedback,
    lint_room,
    lint_scene,
    save_lint_visualization,
)
from scene_builder.validation.rules import LintRule

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
    "format_lint_feedback",
    "save_lint_visualization",
    "IssueTracker",
    "IssueResolver",
    "IssueResolutionOutput",
]
