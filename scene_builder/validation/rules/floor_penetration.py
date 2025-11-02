"""Rule that detects bounding boxes penetrating the floor plane."""

from __future__ import annotations

from collections.abc import Iterable

from scene_builder.validation.context import LintContext, LintingOptions
from scene_builder.validation.models import LintIssue, LintSeverity
from scene_builder.validation.rules.base import LintRule


class FloorPenetrationRule(LintRule):
    """Detect objects whose bounding boxes penetrate the floor plane."""

    code = "floor_penetration"
    description = "Object's bounding box penetrates the floor plane."

    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        floor = options.floor_height
        tolerance = options.floor_tolerance

        for lint_obj in context.objects:
            penetration = floor - lint_obj.bottom
            if penetration <= tolerance:
                continue

            message = (
                f"Object {lint_obj.id}'s bottom surface is {penetration:.3f} m below the "
                f"floor height ({floor:.3f} m)."
            )
            hint = f"Translate {lint_obj.id} upward (+z) by at least {penetration:.3f} m."
            yield LintIssue(
                code=self.code,
                severity=LintSeverity.ERROR,
                object_id=lint_obj.id,
                message=message,
                hint=hint,
                data={
                    "bottom": lint_obj.bottom,
                    "floor_height": floor,
                    "penetration": penetration,
                },
            )

